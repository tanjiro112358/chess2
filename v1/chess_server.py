import socket
import threading
import json
import time
from enum import Enum


class PieceType(Enum):
    PAWN = "pawn"
    ROOK = "rook"
    KNIGHT = "knight"
    BISHOP = "bishop"
    QUEEN = "queen"
    KING = "king"


class PieceColor(Enum):
    WHITE = "white"
    BLACK = "black"


class GameState(Enum):
    WAITING = "waiting"
    PLAYING = "playing"
    FINISHED = "finished"


class ChessPiece:
    def __init__(self, piece_type, color, row, col):
        self.type = piece_type
        self.color = color
        self.row = row
        self.col = col
        self.has_moved = False

    def to_dict(self):
        return {
            'type': self.type.value,
            'color': self.color.value,
            'row': self.row,
            'col': self.col,
            'has_moved': self.has_moved
        }


class ChessGame:
    def __init__(self, game_id):
        self.game_id = game_id
        self.board = [[None for _ in range(9)] for _ in range(9)]
        self.current_player = PieceColor.WHITE
        self.state = GameState.WAITING
        self.players = {}
        self.spectators = []
        self.setup_board()

    def setup_board(self):
        # Setup white pieces (bottom)
        piece_order = [PieceType.ROOK, PieceType.KNIGHT, PieceType.BISHOP, PieceType.QUEEN,
                       PieceType.KING, PieceType.QUEEN, PieceType.BISHOP, PieceType.KNIGHT, PieceType.ROOK]

        for col in range(9):
            self.board[8][col] = ChessPiece(piece_order[col], PieceColor.WHITE, 8, col)
            self.board[7][col] = ChessPiece(PieceType.PAWN, PieceColor.WHITE, 7, col)

        # Setup black pieces (top)
        for col in range(9):
            self.board[0][col] = ChessPiece(piece_order[col], PieceColor.BLACK, 0, col)
            self.board[1][col] = ChessPiece(PieceType.PAWN, PieceColor.BLACK, 1, col)

    def is_valid_move(self, from_row, from_col, to_row, to_col, player_color):
        # Basic bounds checking
        if not (0 <= from_row < 9 and 0 <= from_col < 9 and 0 <= to_row < 9 and 0 <= to_col < 9):
            return False

        piece = self.board[from_row][from_col]
        if not piece or piece.color != player_color:
            return False

        # Can't capture own pieces
        target = self.board[to_row][to_col]
        if target and target.color == player_color:
            return False

        # Piece-specific movement validation
        if not self._validate_piece_movement(piece, from_row, from_col, to_row, to_col):
            return False

        # Check if this move would leave the king in check
        return self.is_move_legal(from_row, from_col, to_row, to_col, player_color)

    def make_move(self, from_row, from_col, to_row, to_col, player_color, promotion_piece=None):
        if not self.is_valid_move(from_row, from_col, to_row, to_col, player_color):
            return False

        piece = self.board[from_row][from_col]
        captured_piece = self.board[to_row][to_col]

        # Move the piece
        self.board[to_row][to_col] = piece
        self.board[from_row][from_col] = None

        piece.row = to_row
        piece.col = to_col
        piece.has_moved = True

        # Check for pawn promotion
        promotion_occurred = False
        if piece.type == PieceType.PAWN:
            promotion_row = 0 if piece.color == PieceColor.WHITE else 8
            if to_row == promotion_row:
                # Promote pawn
                if promotion_piece and promotion_piece in ['queen', 'rook', 'bishop', 'knight']:
                    piece.type = PieceType(promotion_piece)
                    promotion_occurred = True
                else:
                    # Default to queen if no promotion piece specified
                    piece.type = PieceType.QUEEN
                    promotion_occurred = True

        # Switch turns BEFORE checking game status
        self.current_player = PieceColor.BLACK if self.current_player == PieceColor.WHITE else PieceColor.WHITE

        # Check game status after switching turns
        game_status = self.get_game_status()

        return {
            'success': True,
            'promotion': promotion_occurred,
            'promoted_to': piece.type.value if promotion_occurred else None,
            'captured': captured_piece.to_dict() if captured_piece else None,
            'game_status': game_status
        }

    def _validate_piece_movement(self, piece, from_row, from_col, to_row, to_col):
        row_diff = abs(to_row - from_row)
        col_diff = abs(to_col - from_col)

        if piece.type == PieceType.PAWN:
            return self._validate_pawn_move(piece, from_row, from_col, to_row, to_col)
        elif piece.type == PieceType.ROOK:
            return self._validate_rook_move(from_row, from_col, to_row, to_col)
        elif piece.type == PieceType.KNIGHT:
            return (row_diff == 2 and col_diff == 1) or (row_diff == 1 and col_diff == 2)
        elif piece.type == PieceType.BISHOP:
            return self._validate_bishop_move(from_row, from_col, to_row, to_col)
        elif piece.type == PieceType.QUEEN:
            return (self._validate_rook_move(from_row, from_col, to_row, to_col) or
                    self._validate_bishop_move(from_row, from_col, to_row, to_col))
        elif piece.type == PieceType.KING:
            return row_diff <= 1 and col_diff <= 1 and (row_diff + col_diff > 0)

        return False

    def _validate_pawn_move(self, piece, from_row, from_col, to_row, to_col):
        direction = -1 if piece.color == PieceColor.WHITE else 1
        row_diff = to_row - from_row
        col_diff = abs(to_col - from_col)

        # Forward move (no capture)
        if col_diff == 0:
            if row_diff == direction and not self.board[to_row][to_col]:
                return True
            # Double move from starting position
            if (not piece.has_moved and row_diff == 2 * direction and
                    not self.board[to_row][to_col] and not self.board[from_row + direction][from_col]):
                return True
        # Diagonal capture
        elif col_diff == 1 and row_diff == direction:
            # For regular move validation, there must be an enemy piece to capture
            target_piece = self.board[to_row][to_col]
            if target_piece and target_piece.color != piece.color:
                return True

        return False

    def _validate_rook_move(self, from_row, from_col, to_row, to_col):
        if from_row != to_row and from_col != to_col:
            return False
        return self._is_path_clear(from_row, from_col, to_row, to_col)

    def _validate_bishop_move(self, from_row, from_col, to_row, to_col):
        if abs(to_row - from_row) != abs(to_col - from_col):
            return False
        return self._is_path_clear(from_row, from_col, to_row, to_col)

    def _is_path_clear(self, from_row, from_col, to_row, to_col):
        row_step = 0 if from_row == to_row else (1 if to_row > from_row else -1)
        col_step = 0 if from_col == to_col else (1 if to_col > from_col else -1)

        current_row, current_col = from_row + row_step, from_col + col_step

        while current_row != to_row or current_col != to_col:
            if self.board[current_row][current_col]:
                return False
            current_row += row_step
            current_col += col_step

        return True

    def find_king(self, color):
        """Find the king of the specified color"""
        for row in range(9):
            for col in range(9):
                piece = self.board[row][col]
                if piece and piece.type == PieceType.KING and piece.color == color:
                    return (row, col)
        return None

    def is_square_attacked(self, row, col, attacking_color):
        """Check if a square is attacked by any piece of the attacking color"""
        for r in range(9):
            for c in range(9):
                piece = self.board[r][c]
                if piece and piece.color == attacking_color:
                    if self._can_piece_attack_square(piece, r, c, row, col):
                        return True
        return False

    def _can_piece_attack_square(self, piece, from_row, from_col, target_row, target_col):
        """Check if a piece can attack a specific square"""
        # Special handling for pawns since they attack differently than they move
        if piece.type == PieceType.PAWN:
            return self._can_pawn_attack_square(piece, from_row, from_col, target_row, target_col)

        # For other pieces, temporarily remove the target piece to check if it can be attacked
        original_piece = self.board[target_row][target_col]
        self.board[target_row][target_col] = None

        can_attack = self._validate_piece_movement(piece, from_row, from_col, target_row, target_col)

        # Restore the original piece
        self.board[target_row][target_col] = original_piece

        return can_attack

    def _can_pawn_attack_square(self, pawn, from_row, from_col, target_row, target_col):
        """Check if a pawn can attack a specific square"""
        direction = -1 if pawn.color == PieceColor.WHITE else 1

        # Pawn attacks diagonally one square forward
        if target_row == from_row + direction:
            if abs(target_col - from_col) == 1:
                return True

        return False

    def is_in_check(self, color):
        """Check if the king of the specified color is in check"""
        king_pos = self.find_king(color)
        if not king_pos:
            print(f"Warning: No king found for {color.value}")
            return False

        enemy_color = PieceColor.BLACK if color == PieceColor.WHITE else PieceColor.WHITE
        king_row, king_col = king_pos

        # Check if any enemy piece can attack the king
        for row in range(9):
            for col in range(9):
                piece = self.board[row][col]
                if piece and piece.color == enemy_color:
                    if self._can_piece_attack_square(piece, row, col, king_row, king_col):
                        print(
                            f"{color.value} king at ({king_row}, {king_col}) is in check from {piece.type.value} at ({row}, {col})")
                        return True

        return False

    def is_move_legal(self, from_row, from_col, to_row, to_col, color):
        """Check if a move is legal (doesn't leave king in check)"""
        # Make the move temporarily
        piece = self.board[from_row][from_col]
        captured = self.board[to_row][to_col]

        self.board[to_row][to_col] = piece
        self.board[from_row][from_col] = None

        # Check if king is in check after this move
        king_safe = not self.is_in_check(color)

        # Restore the board
        self.board[from_row][from_col] = piece
        self.board[to_row][to_col] = captured

        return king_safe

    def get_legal_moves(self, color):
        """Get all legal moves (that don't leave king in check)"""
        legal_moves = []

        for row in range(9):
            for col in range(9):
                piece = self.board[row][col]
                if piece and piece.color == color:
                    # Get all possible moves for this piece
                    for target_row in range(9):
                        for target_col in range(9):
                            if self.is_valid_move(row, col, target_row, target_col, color):
                                # Make the move temporarily to see if it leaves king in check
                                original_piece = self.board[target_row][target_col]
                                self.board[target_row][target_col] = piece
                                self.board[row][col] = None

                                # Check if king is safe after this move
                                king_safe = not self.is_in_check(color)

                                # Restore the board
                                self.board[row][col] = piece
                                self.board[target_row][target_col] = original_piece

                                if king_safe:
                                    legal_moves.append((row, col, target_row, target_col))

        print(f"{color.value} has {len(legal_moves)} legal moves")
        return legal_moves

    def is_checkmate(self, color):
        """Check if the specified color is in checkmate"""
        if not self.is_in_check(color):
            return False

        # If in check, see if there are any legal moves
        legal_moves = self.get_legal_moves(color)
        return len(legal_moves) == 0

    def is_stalemate(self, color):
        """Check if the specified color is in stalemate"""
        if self.is_in_check(color):
            return False

        # If not in check, see if there are any legal moves
        legal_moves = self.get_legal_moves(color)
        return len(legal_moves) == 0

    def get_game_status(self):
        """Get the current game status"""
        current_color = self.current_player

        if self.is_checkmate(current_color):
            winner = PieceColor.BLACK if current_color == PieceColor.WHITE else PieceColor.WHITE
            loser = current_color
            return {
                'status': 'checkmate',
                'winner': winner.value,
                'loser': loser.value,
                'message': f'Checkmate! {winner.value.title()} wins!',
                'in_checkmate': loser.value
            }
        elif self.is_stalemate(current_color):
            return {
                'status': 'stalemate',
                'message': 'Stalemate! Game is a draw.'
            }
        elif self.is_in_check(current_color):
            return {
                'status': 'check',
                'in_check': current_color.value,
                'message': f'{current_color.value.title()} is in check!'
            }
        else:
            return {
                'status': 'playing',
                'message': 'Game continues.'
            }
        if not self.is_valid_move(from_row, from_col, to_row, to_col, player_color):
            return False

        piece = self.board[from_row][from_col]
        captured_piece = self.board[to_row][to_col]

        # Move the piece
        self.board[to_row][to_col] = piece
        self.board[from_row][from_col] = None

        piece.row = to_row
        piece.col = to_col
        piece.has_moved = True

        # Check for pawn promotion
        promotion_occurred = False
        if piece.type == PieceType.PAWN:
            promotion_row = 0 if piece.color == PieceColor.WHITE else 8
            if to_row == promotion_row:
                # Promote pawn
                if promotion_piece and promotion_piece in ['queen', 'rook', 'bishop', 'knight']:
                    piece.type = PieceType(promotion_piece)
                    promotion_occurred = True
                else:
                    # Default to queen if no promotion piece specified
                    piece.type = PieceType.QUEEN
                    promotion_occurred = True

        # Switch turns
        self.current_player = PieceColor.BLACK if self.current_player == PieceColor.WHITE else PieceColor.WHITE

        return {
            'success': True,
            'promotion': promotion_occurred,
            'promoted_to': piece.type.value if promotion_occurred else None,
            'captured': captured_piece.to_dict() if captured_piece else None
        }

    def get_board_state(self):
        board_data = []
        for row in self.board:
            row_data = []
            for piece in row:
                row_data.append(piece.to_dict() if piece else None)
            board_data.append(row_data)
        return board_data


class ChessServer:
    def __init__(self, host='localhost', port=8888):
        self.host = host
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.clients = {}
        self.games = {}
        self.waiting_players = []
        self.game_counter = 0

    def start(self):
        self.socket.bind((self.host, self.port))
        self.socket.listen(5)
        print(f"Chess server started on {self.host}:{self.port}")

        while True:
            try:
                client_socket, address = self.socket.accept()
                client_id = f"client_{len(self.clients)}"
                self.clients[client_id] = {
                    'socket': client_socket,
                    'address': address,
                    'game_id': None,
                    'color': None
                }

                thread = threading.Thread(target=self.handle_client, args=(client_id,))
                thread.daemon = True
                thread.start()

                print(f"Client {client_id} connected from {address}")
            except Exception as e:
                print(f"Error accepting client: {e}")

    def handle_client(self, client_id):
        client = self.clients[client_id]
        socket_obj = client['socket']
        buffer = ""

        try:
            while True:
                data = socket_obj.recv(1024).decode('utf-8')
                if not data:
                    break

                buffer += data

                # Process complete JSON messages
                while buffer:
                    try:
                        # Try to find a complete JSON message
                        message = json.loads(buffer.strip())
                        print(f"Received from {client_id}: {message}")
                        self.process_message(client_id, message)
                        buffer = ""
                        break
                    except json.JSONDecodeError:
                        # If JSON is incomplete, wait for more data
                        if len(buffer) > 10000:  # Prevent buffer overflow
                            buffer = ""
                        break

        except Exception as e:
            print(f"Error handling client {client_id}: {e}")
        finally:
            self.disconnect_client(client_id)

    def process_message(self, client_id, message):
        msg_type = message.get('type')
        print(f"Processing message from {client_id}: {msg_type}")

        if msg_type == 'join_queue':
            self.add_to_queue(client_id)
        elif msg_type == 'move':
            self.handle_move(client_id, message)
        elif msg_type == 'spectate':
            self.handle_spectate(client_id, message)
        else:
            print(f"Unknown message type: {msg_type}")

    def add_to_queue(self, client_id):
        if client_id not in self.waiting_players:
            self.waiting_players.append(client_id)
            print(f"Added {client_id} to queue. Queue length: {len(self.waiting_players)}")
            self.send_message(client_id, {'type': 'queue_joined', 'position': len(self.waiting_players)})

            if len(self.waiting_players) >= 2:
                print("Enough players in queue, creating game...")
                self.create_game()

    def create_game(self):
        if len(self.waiting_players) < 2:
            return

        player1_id = self.waiting_players.pop(0)
        player2_id = self.waiting_players.pop(0)

        print(f"Creating game between {player1_id} and {player2_id}")

        self.game_counter += 1
        game_id = f"game_{self.game_counter}"
        game = ChessGame(game_id)

        self.games[game_id] = game

        # Assign colors
        self.clients[player1_id]['game_id'] = game_id
        self.clients[player1_id]['color'] = PieceColor.WHITE
        self.clients[player2_id]['game_id'] = game_id
        self.clients[player2_id]['color'] = PieceColor.BLACK

        game.players[PieceColor.WHITE] = player1_id
        game.players[PieceColor.BLACK] = player2_id
        game.state = GameState.PLAYING

        print(f"Game {game_id} created, sending start messages...")

        # Notify players
        self.send_game_start(player1_id, game_id, PieceColor.WHITE)
        self.send_game_start(player2_id, game_id, PieceColor.BLACK)

        print(f"Game start messages sent for {game_id}")

    def send_game_start(self, client_id, game_id, color):
        game = self.games[game_id]
        message = {
            'type': 'game_start',
            'game_id': game_id,
            'color': color.value,
            'board': game.get_board_state(),
            'current_player': game.current_player.value
        }
        self.send_message(client_id, message)

    def handle_move(self, client_id, message):
        client = self.clients[client_id]
        game_id = client['game_id']

        if not game_id or game_id not in self.games:
            self.send_error(client_id, "Not in a game")
            return

        game = self.games[game_id]
        player_color = client['color']

        if game.current_player != player_color:
            self.send_error(client_id, "Not your turn")
            return

        from_row = message['from_row']
        from_col = message['from_col']
        to_row = message['to_row']
        to_col = message['to_col']
        promotion_piece = message.get('promotion_piece', None)

        result = game.make_move(from_row, from_col, to_row, to_col, player_color, promotion_piece)

        if result and result['success']:
            game_status = result['game_status']

            # Broadcast move to all players and spectators
            move_message = {
                'type': 'move_made',
                'from_row': from_row,
                'from_col': from_col,
                'to_row': to_row,
                'to_col': to_col,
                'board': game.get_board_state(),
                'current_player': game.current_player.value,
                'promotion': result.get('promotion', False),
                'promoted_to': result.get('promoted_to', None),
                'captured': result.get('captured', None),
                'game_status': game_status
            }

            for color, pid in game.players.items():
                self.send_message(pid, move_message)

            for spectator_id in game.spectators:
                self.send_message(spectator_id, move_message)

            # Handle game end
            if game_status['status'] in ['checkmate', 'stalemate']:
                game.state = GameState.FINISHED

                print(f"Game {game_id} ended: {game_status['status']}")
                print(f"Current player after move: {game.current_player.value}")
                print(f"Winner: {game_status.get('winner')}, Loser: {game_status.get('loser')}")

                # Create game end message
                end_message = {
                    'type': 'game_end',
                    'status': game_status['status'],
                    'winner': game_status.get('winner'),
                    'loser': game_status.get('loser'),
                    'message': game_status['message']
                }

                print(f"Sending game end message: {end_message}")

                # Send to both players with verification - DO NOT reset their game state yet
                players_notified = 0
                for color, pid in game.players.items():
                    if pid in self.clients:
                        print(f"Sending game end to player {pid} (color: {color.value})")
                        print(f"  - Player is {'WINNER' if color.value == game_status.get('winner') else 'LOSER'}")

                        # Send the message multiple times with small delays
                        import time
                        for attempt in range(3):
                            try:
                                success = self.send_message(pid, end_message)
                                if success:
                                    print(f"  - Message sent successfully to {pid} on attempt {attempt + 1}")
                                    players_notified += 1
                                    time.sleep(0.1)  # Small delay between attempts
                                    break
                                else:
                                    print(f"  - Failed to send message to {pid} on attempt {attempt + 1}")
                                    time.sleep(0.1)
                            except Exception as e:
                                print(f"  - Exception sending to {pid} on attempt {attempt + 1}: {e}")
                                time.sleep(0.1)

                        # DON'T reset game state here - let client handle disconnection
                    else:
                        print(f"  - Player {pid} not found in clients")

                print(f"Successfully notified {players_notified} players")

                # Send to spectators
                for spectator_id in game.spectators:
                    if spectator_id in self.clients:
                        self.send_message(spectator_id, end_message)

                # DON'T delete the game immediately - let it timeout naturally
                # This prevents connection issues when clients are still processing
                print(f"Game {game_id} marked as finished - will be cleaned up later")
        else:
            self.send_error(client_id, "Invalid move")

    def send_message(self, client_id, message):
        try:
            if client_id in self.clients:
                socket_obj = self.clients[client_id]['socket']
                message_str = json.dumps(message)
                print(f"Sending to {client_id}: {message_str}")
                socket_obj.send(message_str.encode('utf-8'))
                return True
            else:
                print(f"Client {client_id} not found in clients list")
                return False
        except Exception as e:
            print(f"Error sending message to {client_id}: {e}")
            self.disconnect_client(client_id)
            return False

    def send_error(self, client_id, error_message):
        self.send_message(client_id, {'type': 'error', 'message': error_message})

    def cleanup_game(self, game_id):
        """Clean up a finished game"""
        if game_id in self.games:
            game = self.games[game_id]
            print(f"Cleaning up game {game_id}")

            # Reset all players' game state gently
            for color, pid in game.players.items():
                if pid in self.clients:
                    self.clients[pid]['game_id'] = None
                    self.clients[pid]['color'] = None
                    print(f"Reset game state for player {pid}")

            del self.games[game_id]
            print(f"Game {game_id} cleaned up successfully")

    def start_cleanup_timer(self, game_id):
        """Start a cleanup timer for a finished game"""
        import threading
        def delayed_cleanup():
            self.cleanup_game(game_id)

        # Wait 5 seconds before cleanup to let clients process messages
        threading.Timer(5.0, delayed_cleanup).start()
        print(f"Started cleanup timer for game {game_id}")

    def disconnect_client(self, client_id):
        if client_id in self.clients:
            client = self.clients[client_id]

            print(f"Disconnecting client {client_id}")

            # Remove from waiting queue
            if client_id in self.waiting_players:
                self.waiting_players.remove(client_id)
                print(f"Removed {client_id} from waiting queue")

            # Handle game disconnection more gracefully
            game_id = client.get('game_id')
            if game_id and game_id in self.games:
                game = self.games[game_id]
                print(f"Client {client_id} was in game {game_id}")

                # Don't immediately clean up - just notify other players
                for color, pid in game.players.items():
                    if pid != client_id and pid in self.clients:
                        print(f"Notifying {pid} that {client_id} disconnected")
                        self.send_message(pid, {'type': 'opponent_disconnected'})

                # Mark game for cleanup but don't delete immediately
                game.state = GameState.FINISHED
                self.start_cleanup_timer(game_id)

            # Close socket gently
            try:
                client['socket'].shutdown(socket.SHUT_RDWR)
            except:
                pass

            try:
                client['socket'].close()
            except:
                pass

            del self.clients[client_id]
            print(f"Client {client_id} disconnected and cleaned up")


if __name__ == "__main__":
    server = ChessServer()
    try:
        server.start()
    except KeyboardInterrupt:
        print("\nServer shutting down...")
    except Exception as e:
        print(f"Server error: {e}")