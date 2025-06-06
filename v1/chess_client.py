import pygame
import socket
import json
import threading
import sys
import os
from enum import Enum

# Initialize Pygame
pygame.init()

# Constants
BOARD_SIZE = 9
CELL_SIZE = 60
BOARD_WIDTH = BOARD_SIZE * CELL_SIZE
BOARD_HEIGHT = BOARD_SIZE * CELL_SIZE
SIDEBAR_WIDTH = 300
WINDOW_WIDTH = BOARD_WIDTH + SIDEBAR_WIDTH
WINDOW_HEIGHT = max(BOARD_HEIGHT, 600)

# Colors
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
LIGHT_BROWN = (240, 217, 181)
DARK_BROWN = (181, 136, 99)
HIGHLIGHT_COLOR = (255, 255, 0, 128)
VALID_MOVE_COLOR = (0, 255, 0, 128)
SELECTED_COLOR = (255, 0, 0, 128)
CHECK_COLOR = (255, 100, 100)
BUTTON_COLOR = (70, 130, 180)
BUTTON_HOVER = (100, 149, 237)
TEXT_COLOR = (50, 50, 50)


class GameState(Enum):
    MENU = "menu"
    WAITING = "waiting"
    PLAYING = "playing"
    GAME_END = "game_end"


class ChessClient:
    def __init__(self):
        # Game loop control
        self.running = True

        # Initialize Pygame display
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("Chess 9x9 Online")
        self.clock = pygame.time.Clock()

        # Network state
        self.socket = None
        self.connected = False

        # Core game state
        self.state = GameState.MENU
        self.board = [[None for _ in range(9)] for _ in range(9)]
        self.selected_piece = None
        self.valid_moves = []
        self.current_player = "white"
        self.player_color = None
        self.game_id = None

        # Game status flags
        self.in_check = False
        self.game_end_message = ""
        self.game_end_timer = 0
        self.last_move_time = 0  # Track when last move was made
        self.stuck_check_timer = 0  # Timer to check for stuck states

        # Promotion handling
        self.promotion_pending = False
        self.promotion_move = None
        self.promotion_options = ['queen', 'rook', 'bishop', 'knight']

        # UI fonts
        self.font = pygame.font.Font(None, 24)
        self.title_font = pygame.font.Font(None, 48)
        self.small_font = pygame.font.Font(None, 18)
        self.large_font = pygame.font.Font(None, 36)

        # Message system
        self.messages = []
        self.max_messages = 10

        # Initialize piece sprites
        self.piece_sprites = {}
        self.load_piece_sprites()

    def create_piece_sprite(self, piece_type, color, size=CELL_SIZE - 10):
        """Create a simple colored piece sprite programmatically"""
        sprite = pygame.Surface((size, size), pygame.SRCALPHA)

        # Define colors for pieces
        piece_color = (240, 240, 240) if color == 'white' else (40, 40, 40)
        border_color = (0, 0, 0) if color == 'white' else (200, 200, 200)

        center_x, center_y = size // 2, size // 2

        if piece_type == 'pawn':
            pygame.draw.circle(sprite, piece_color, (center_x, center_y - 5), size // 4)
            pygame.draw.rect(sprite, piece_color, (center_x - size // 6, center_y + 5, size // 3, size // 6))
            pygame.draw.circle(sprite, border_color, (center_x, center_y - 5), size // 4, 2)

        elif piece_type == 'rook':
            base_height = size // 2
            pygame.draw.rect(sprite, piece_color, (center_x - size // 4, center_y, size // 2, base_height))
            for i in range(3):
                x = center_x - size // 4 + i * size // 6
                pygame.draw.rect(sprite, piece_color, (x, center_y - size // 6, size // 8, size // 6))
            pygame.draw.rect(sprite, border_color, (center_x - size // 4, center_y, size // 2, base_height), 2)

        elif piece_type == 'knight':
            points = [
                (center_x - size // 6, center_y + size // 4),
                (center_x - size // 4, center_y),
                (center_x - size // 6, center_y - size // 4),
                (center_x + size // 6, center_y - size // 6),
                (center_x + size // 4, center_y + size // 6),
                (center_x + size // 6, center_y + size // 4)
            ]
            pygame.draw.polygon(sprite, piece_color, points)
            pygame.draw.polygon(sprite, border_color, points, 2)

        elif piece_type == 'bishop':
            pygame.draw.circle(sprite, piece_color, (center_x, center_y + 5), size // 5)
            points = [
                (center_x, center_y - size // 3),
                (center_x - size // 6, center_y),
                (center_x + size // 6, center_y)
            ]
            pygame.draw.polygon(sprite, piece_color, points)
            pygame.draw.circle(sprite, border_color, (center_x, center_y + 5), size // 5, 2)
            pygame.draw.polygon(sprite, border_color, points, 2)

        elif piece_type == 'queen':
            pygame.draw.circle(sprite, piece_color, (center_x, center_y + 5), size // 4)
            for i in range(5):
                x = center_x - size // 4 + i * size // 8
                height = size // 6 if i % 2 == 0 else size // 8
                pygame.draw.rect(sprite, piece_color, (x, center_y - size // 4, size // 16, height))
            pygame.draw.circle(sprite, border_color, (center_x, center_y + 5), size // 4, 2)

        elif piece_type == 'king':
            pygame.draw.circle(sprite, piece_color, (center_x, center_y + 5), size // 4)
            pygame.draw.rect(sprite, piece_color, (center_x - size // 12, center_y - size // 3, size // 6, size // 4))
            pygame.draw.rect(sprite, piece_color, (center_x - size // 6, center_y - size // 4, size // 3, size // 12))
            pygame.draw.circle(sprite, border_color, (center_x, center_y + 5), size // 4, 2)

        return sprite

    def load_piece_sprites(self):
        """Load or create piece sprites"""
        pieces = ['pawn', 'rook', 'knight', 'bishop', 'queen', 'king']
        colors = ['white', 'black']

        for color in colors:
            self.piece_sprites[color] = {}
            for piece in pieces:
                filename = f"assets/{color}_{piece}.png"
                if os.path.exists(filename):
                    try:
                        sprite = pygame.image.load(filename)
                        sprite = pygame.transform.scale(sprite, (CELL_SIZE - 10, CELL_SIZE - 10))
                        self.piece_sprites[color][piece] = sprite
                        continue
                    except pygame.error:
                        pass

                self.piece_sprites[color][piece] = self.create_piece_sprite(piece, color)

    def create_piece_folder_and_instructions(self):
        """Create pieces folder and instructions for adding PNG files"""
        if not os.path.exists("pieces"):
            os.makedirs("pieces")
            print("Created 'pieces' folder for PNG sprites")

    def reset_to_menu(self):
        """Reset all game state and return to menu"""
        print("Resetting to menu state")
        self.state = GameState.MENU
        self.game_end_message = ""
        self.game_end_timer = 0
        self.in_check = False
        self.selected_piece = None
        self.valid_moves = []
        self.board = [[None for _ in range(9)] for _ in range(9)]
        self.player_color = None
        self.game_id = None
        self.current_player = "white"
        self.promotion_pending = False
        self.promotion_move = None

    # Network methods
    def connect_to_server(self, host='localhost', port=8888):
        try:
            self.create_piece_folder_and_instructions()

            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((host, port))
            self.connected = True

            thread = threading.Thread(target=self.receive_messages)
            thread.daemon = True
            thread.start()

            self.add_message("Connected to server!")
            return True
        except Exception as e:
            self.add_message(f"Connection failed: {e}")
            return False

    def receive_messages(self):
        buffer = ""
        while self.connected:
            try:
                data = self.socket.recv(1024).decode('utf-8')
                if not data:
                    print("No data received, connection closed")
                    break

                buffer += data

                while buffer:
                    try:
                        message = json.loads(buffer.strip())
                        self.handle_server_message(message)
                        buffer = ""
                        break
                    except json.JSONDecodeError:
                        if len(buffer) > 10000:
                            buffer = ""
                        break

            except ConnectionResetError:
                print("Connection reset by server")
                break
            except ConnectionAbortedError:
                print("Connection aborted by server")
                break
            except OSError as e:
                print(f"Socket error: {e}")
                break
            except Exception as e:
                print(f"Error receiving message: {e}")
                break

        print("Message receiving loop ended")
        self.connected = False

        # If we were in a game and connection dropped, show appropriate message
        if self.state == GameState.PLAYING:
            print("Connection lost during game, checking if game ended...")
            # Don't immediately reset - let the user see what happened
            self.add_message("Connection lost - game may have ended")

            # Set a timer to return to menu after a delay
            self.game_end_message = "Connection Lost\nReturning to menu..."
            self.game_end_timer = pygame.time.get_ticks() + 4000  # 3 seconds
            self.state = GameState.GAME_END

    def handle_server_message(self, message):
        msg_type = message.get('type')
        print(f"Received message: {msg_type}")

        if msg_type == 'queue_joined':
            self.state = GameState.WAITING
            position = message.get('position', 0)
            self.add_message(f"Joined queue (position {position})")

        elif msg_type == 'game_start':
            print(f"Game starting: {message}")
            self.state = GameState.PLAYING
            self.game_id = message['game_id']
            self.player_color = message['color']
            self.board = message['board']
            self.current_player = message['current_player']
            self.add_message(f"Game started! You are {self.player_color}")

        elif msg_type == 'move_made':
            self.board = message['board']
            self.current_player = message['current_player']
            self.selected_piece = None
            self.valid_moves = []
            self.last_move_time = pygame.time.get_ticks()  # Update last move time

            # Handle game status
            game_status = message.get('game_status', {})
            status = game_status.get('status', 'playing')

            print(f"Game status: {status}")

            if status == 'check':
                self.in_check = True
                check_color = game_status.get('in_check', 'unknown')
                self.add_message(f"{check_color.title()} is in check!")
                print(f"Check detected: {check_color} is in check")
            elif status == 'checkmate':
                print(f"Checkmate detected in move_made message!")
                # Sometimes the game_end message doesn't arrive, so handle it here too
                winner = game_status.get('winner')
                loser = game_status.get('loser')

                if winner == self.player_color:
                    self.game_end_message = f"🎉 YOU WIN! 🎉\nCheckmate!"
                elif loser == self.player_color:
                    self.game_end_message = f"💔 YOU LOSE 💔\nCheckmate!"
                else:
                    # Fallback logic
                    if self.current_player != self.player_color:
                        self.game_end_message = f"🎉 YOU WIN! 🎉\nCheckmate!"
                    else:
                        self.game_end_message = f"💔 YOU LOSE 💔\nCheckmate!"

                self.game_end_timer = pygame.time.get_ticks() + 4000
                self.state = GameState.GAME_END
                print(f"Set game end from move_made: {self.game_end_message}")
            elif status == 'stalemate':
                print(f"Stalemate detected in move_made message!")
                self.game_end_message = f"🤝 DRAW 🤝\nStalemate!"
                self.game_end_timer = pygame.time.get_ticks() + 4000
                self.state = GameState.GAME_END
            else:
                self.in_check = False

            # Handle promotion notification
            if message.get('promotion', False):
                promoted_to = message.get('promoted_to', 'queen')
                self.add_message(f"Pawn promoted to {promoted_to}!")

            # Handle capture notification
            if message.get('captured'):
                captured_piece = message['captured']
                self.add_message(f"Captured {captured_piece['color']} {captured_piece['type']}!")

        elif msg_type == 'game_end':
            status = message['status']
            winner = message.get('winner')
            loser = message.get('loser')
            game_message = message['message']

            print(f"=== GAME END MESSAGE RECEIVED ===")
            print(f"Status: {status}")
            print(f"Winner: {winner}")
            print(f"Loser: {loser}")
            print(f"My color: {self.player_color}")
            print(f"Message: {game_message}")

            # Reset game state immediately
            self.selected_piece = None
            self.valid_moves = []
            self.promotion_pending = False
            self.promotion_move = None
            self.in_check = False

            if status == 'checkmate':
                if winner == self.player_color:
                    self.game_end_message = f"🎉 YOU WIN! 🎉\n{game_message}"
                    print("I WON!")
                elif loser == self.player_color:
                    self.game_end_message = f"💔 YOU LOSE 💔\n{game_message}"
                    print("I LOST!")
                else:
                    # Fallback - shouldn't happen but just in case
                    self.game_end_message = f"Game Over\n{game_message}"
                    print("Game ended - unclear result")
            elif status == 'stalemate':
                self.game_end_message = f"🤝 DRAW 🤝\n{game_message}"
                print("DRAW!")

            self.add_message(game_message)
            self.game_end_timer = pygame.time.get_ticks() + 4000  # 2 seconds
            self.state = GameState.GAME_END

            print(f"Set game end state with message: {self.game_end_message}")
            print("=== END GAME END MESSAGE ===\n")

        elif msg_type == 'error':
            self.add_message(f"Error: {message['message']}")

        elif msg_type == 'opponent_disconnected':
            self.add_message("Opponent disconnected")
            print("Opponent disconnected, returning to menu")
            # Give a brief moment to see the message, then return to menu
            self.game_end_message = "Opponent Disconnected\nGame ended"
            self.game_end_timer = pygame.time.get_ticks() + 4000  # 4 seconds
            self.state = GameState.GAME_END

    def send_message(self, message):
        if self.connected:
            try:
                self.socket.send(json.dumps(message).encode('utf-8'))
            except Exception as e:
                print(f"Error sending message: {e}")

    def add_message(self, text):
        self.messages.append(text)
        if len(self.messages) > self.max_messages:
            self.messages.pop(0)

    def join_queue(self):
        if self.connected:
            self.send_message({'type': 'join_queue'})

    # Game logic methods
    def needs_promotion(self, from_row, from_col, to_row, to_col):
        """Check if a move will result in pawn promotion"""
        piece = self.board[from_row][from_col]
        if piece and piece['type'] == 'pawn':
            promotion_row = 0 if piece['color'] == 'white' else 8
            return to_row == promotion_row
        return False

    def make_move(self, from_row, from_col, to_row, to_col, promotion_piece=None):
        if self.connected and self.state == GameState.PLAYING:
            move_message = {
                'type': 'move',
                'from_row': from_row,
                'from_col': from_col,
                'to_row': to_row,
                'to_col': to_col
            }

            if promotion_piece:
                move_message['promotion_piece'] = promotion_piece

            self.send_message(move_message)

    def handle_promotion_choice(self, choice):
        """Handle the player's promotion choice"""
        if self.promotion_pending and self.promotion_move:
            from_row, from_col, to_row, to_col = self.promotion_move
            self.make_move(from_row, from_col, to_row, to_col, choice)
            self.promotion_pending = False
            self.promotion_move = None

    def get_valid_moves(self, row, col):
        """Calculate valid moves for a piece based on chess rules"""
        valid_moves = []
        piece = self.board[row][col]

        if not piece:
            return valid_moves

        piece_type = piece['type']
        piece_color = piece['color']

        if piece_type == 'pawn':
            valid_moves = self._get_pawn_moves(row, col, piece_color)
        elif piece_type == 'rook':
            valid_moves = self._get_rook_moves(row, col, piece_color)
        elif piece_type == 'knight':
            valid_moves = self._get_knight_moves(row, col, piece_color)
        elif piece_type == 'bishop':
            valid_moves = self._get_bishop_moves(row, col, piece_color)
        elif piece_type == 'queen':
            valid_moves = self._get_queen_moves(row, col, piece_color)
        elif piece_type == 'king':
            valid_moves = self._get_king_moves(row, col, piece_color)

        return valid_moves

    def _get_pawn_moves(self, row, col, color):
        """Get valid pawn moves"""
        moves = []
        direction = -1 if color == 'white' else 1
        start_row = 7 if color == 'white' else 1

        # Forward move
        new_row = row + direction
        if 0 <= new_row < 9 and not self.board[new_row][col]:
            moves.append((new_row, col))

            # Double move from starting position
            if row == start_row and not self.board[new_row + direction][col]:
                moves.append((new_row + direction, col))

        # Diagonal captures
        for dc in [-1, 1]:
            new_row, new_col = row + direction, col + dc
            if (0 <= new_row < 9 and 0 <= new_col < 9 and
                    self.board[new_row][new_col] and
                    self.board[new_row][new_col]['color'] != color):
                moves.append((new_row, new_col))

        return moves

    def _get_rook_moves(self, row, col, color):
        """Get valid rook moves (straight lines)"""
        moves = []
        directions = [(0, 1), (0, -1), (1, 0), (-1, 0)]

        for dr, dc in directions:
            for i in range(1, 9):
                new_row, new_col = row + dr * i, col + dc * i

                if not (0 <= new_row < 9 and 0 <= new_col < 9):
                    break

                target = self.board[new_row][new_col]
                if target:
                    if target['color'] != color:
                        moves.append((new_row, new_col))
                    break
                else:
                    moves.append((new_row, new_col))

        return moves

    def _get_knight_moves(self, row, col, color):
        """Get valid knight moves (L-shaped)"""
        moves = []
        knight_moves = [
            (-2, -1), (-2, 1), (-1, -2), (-1, 2),
            (1, -2), (1, 2), (2, -1), (2, 1)
        ]

        for dr, dc in knight_moves:
            new_row, new_col = row + dr, col + dc

            if 0 <= new_row < 9 and 0 <= new_col < 9:
                target = self.board[new_row][new_col]
                if not target or target['color'] != color:
                    moves.append((new_row, new_col))

        return moves

    def _get_bishop_moves(self, row, col, color):
        """Get valid bishop moves (diagonal lines)"""
        moves = []
        directions = [(1, 1), (1, -1), (-1, 1), (-1, -1)]

        for dr, dc in directions:
            for i in range(1, 9):
                new_row, new_col = row + dr * i, col + dc * i

                if not (0 <= new_row < 9 and 0 <= new_col < 9):
                    break

                target = self.board[new_row][new_col]
                if target:
                    if target['color'] != color:
                        moves.append((new_row, new_col))
                    break
                else:
                    moves.append((new_row, new_col))

        return moves

    def _get_queen_moves(self, row, col, color):
        """Get valid queen moves (combination of rook and bishop)"""
        moves = []
        moves.extend(self._get_rook_moves(row, col, color))
        moves.extend(self._get_bishop_moves(row, col, color))
        return moves

    def _get_king_moves(self, row, col, color):
        """Get valid king moves (one square in any direction)"""
        moves = []
        directions = [
            (-1, -1), (-1, 0), (-1, 1),
            (0, -1), (0, 1),
            (1, -1), (1, 0), (1, 1)
        ]

        for dr, dc in directions:
            new_row, new_col = row + dr, col + dc

            if 0 <= new_row < 9 and 0 <= new_col < 9:
                target = self.board[new_row][new_col]
                if not target or target['color'] != color:
                    moves.append((new_row, new_col))

        return moves

    def select_piece(self, row, col):
        """Select a piece if it belongs to the current player and it's their turn"""
        piece = self.board[row][col]

        if self.current_player != self.player_color:
            self.add_message("It's not your turn!")
            return

        if piece and piece['color'] == self.player_color:
            self.selected_piece = (row, col)
            self.valid_moves = self.get_valid_moves(row, col)
            if not self.valid_moves:
                self.add_message("This piece has no valid moves!")
        else:
            self.selected_piece = None
            self.valid_moves = []
            if piece and piece['color'] != self.player_color:
                self.add_message("That's not your piece!")

    # Input handling
    def handle_click(self, pos):
        """Handle mouse clicks on the board"""
        if self.promotion_pending:
            self.handle_promotion_dialog_click(pos)
            return

        if self.state == GameState.PLAYING:
            board_x, board_y = pos
            if 0 <= board_x < BOARD_WIDTH and 0 <= board_y < BOARD_HEIGHT:
                col = board_x // CELL_SIZE
                row = board_y // CELL_SIZE

                if self.selected_piece:
                    from_row, from_col = self.selected_piece

                    if (row, col) == (from_row, from_col):
                        self.selected_piece = None
                        self.valid_moves = []
                        return

                    if (row, col) in self.valid_moves:
                        if self.needs_promotion(from_row, from_col, row, col):
                            self.promotion_pending = True
                            self.promotion_move = (from_row, from_col, row, col)
                            self.add_message("Choose promotion piece!")
                        else:
                            self.make_move(from_row, from_col, row, col)
                            self.add_message(
                                f"Move: {chr(ord('a') + from_col)}{9 - from_row} to {chr(ord('a') + col)}{9 - row}")
                    else:
                        self.select_piece(row, col)
                else:
                    self.select_piece(row, col)

    def handle_menu_click(self, pos):
        if not self.connected:
            connect_button = pygame.Rect(WINDOW_WIDTH // 2 - 100, 200, 200, 50)
            if connect_button.collidepoint(pos):
                self.connect_to_server()

        if self.connected and self.state == GameState.MENU:
            queue_button = pygame.Rect(WINDOW_WIDTH // 2 - 100, 270, 200, 50)
            if queue_button.collidepoint(pos):
                self.join_queue()

    def handle_promotion_dialog_click(self, pos):
        """Handle clicks on the promotion dialog"""
        if not self.promotion_pending:
            return

        dialog_width = 400
        dialog_height = 200
        dialog_x = (WINDOW_WIDTH - dialog_width) // 2
        dialog_y = (WINDOW_HEIGHT - dialog_height) // 2

        option_size = 60
        spacing = 80
        start_x = dialog_x + (dialog_width - (len(self.promotion_options) * spacing - 20)) // 2
        option_y = dialog_y + 90

        click_x, click_y = pos

        for i, piece_type in enumerate(self.promotion_options):
            option_x = start_x + i * spacing

            if (option_x <= click_x <= option_x + option_size and
                    option_y <= click_y <= option_y + option_size):
                self.handle_promotion_choice(piece_type)
                return

    # Drawing methods
    def draw_board(self):
        # Draw coordinate labels
        coord_font = pygame.font.Font(None, 16)

        for col in range(BOARD_SIZE):
            x = col * CELL_SIZE + CELL_SIZE // 2
            label = chr(ord('a') + col)
            text = coord_font.render(label, True, TEXT_COLOR)
            text_rect = text.get_rect(center=(x, BOARD_HEIGHT + 10))
            self.screen.blit(text, text_rect)

        for row in range(BOARD_SIZE):
            y = row * CELL_SIZE + CELL_SIZE // 2
            label = str(9 - row)
            text = coord_font.render(label, True, TEXT_COLOR)
            text_rect = text.get_rect(center=(-15, y))
            self.screen.blit(text, text_rect)

        # Draw board squares
        for row in range(BOARD_SIZE):
            for col in range(BOARD_SIZE):
                x = col * CELL_SIZE
                y = row * CELL_SIZE

                # Checkerboard pattern
                color = LIGHT_BROWN if (row + col) % 2 == 0 else DARK_BROWN

                # Highlight king in check
                piece = self.board[row][col] if self.board and len(self.board) > row else None
                if (piece and piece['type'] == 'king' and piece['color'] == self.current_player
                        and self.in_check):
                    color = CHECK_COLOR

                pygame.draw.rect(self.screen, color, (x, y, CELL_SIZE, CELL_SIZE))

                # Highlight selected piece
                if self.selected_piece and self.selected_piece == (row, col):
                    highlight_surface = pygame.Surface((CELL_SIZE, CELL_SIZE), pygame.SRCALPHA)
                    highlight_surface.fill(SELECTED_COLOR)
                    self.screen.blit(highlight_surface, (x, y))

                # Highlight valid moves
                if (row, col) in self.valid_moves:
                    highlight_surface = pygame.Surface((CELL_SIZE, CELL_SIZE), pygame.SRCALPHA)
                    highlight_surface.fill(VALID_MOVE_COLOR)
                    self.screen.blit(highlight_surface, (x, y))

                    if not piece:
                        center = (x + CELL_SIZE // 2, y + CELL_SIZE // 2)
                        pygame.draw.circle(self.screen, (0, 200, 0), center, 8)
                    else:
                        pygame.draw.rect(self.screen, (200, 0, 0), (x, y, CELL_SIZE, CELL_SIZE), 4)

                # Draw piece
                if piece:
                    sprite = self.piece_sprites[piece['color']][piece['type']]
                    sprite_rect = sprite.get_rect(center=(x + CELL_SIZE // 2, y + CELL_SIZE // 2))
                    self.screen.blit(sprite, sprite_rect)

    def draw_sidebar(self):
        sidebar_x = BOARD_WIDTH
        sidebar_rect = pygame.Rect(sidebar_x, 0, SIDEBAR_WIDTH, WINDOW_HEIGHT)
        pygame.draw.rect(self.screen, WHITE, sidebar_rect)
        pygame.draw.line(self.screen, BLACK, (sidebar_x, 0), (sidebar_x, WINDOW_HEIGHT), 2)

        y_offset = 20

        # Title
        title_text = self.title_font.render("Chess 9x9", True, TEXT_COLOR)
        self.screen.blit(title_text, (sidebar_x + 20, y_offset))
        y_offset += 60

        # Game status
        if self.state == GameState.MENU:
            status_text = "Main Menu"
            status_color = TEXT_COLOR
        elif self.state == GameState.WAITING:
            status_text = "Waiting for opponent..."
            status_color = (255, 165, 0)
        elif self.state == GameState.PLAYING:
            if self.in_check:
                if self.current_player == self.player_color:
                    status_text = "YOU ARE IN CHECK!"
                    status_color = (255, 0, 0)
                else:
                    status_text = "Opponent in check"
                    status_color = (255, 165, 0)
            elif self.current_player == self.player_color:
                status_text = f"Your turn ({self.player_color})"
                status_color = (0, 128, 0)
            else:
                status_text = "Opponent's turn"
                status_color = (128, 0, 0)
        elif self.state == GameState.GAME_END:
            status_text = "Game Ended"
            status_color = TEXT_COLOR
        else:
            status_text = "Unknown State"
            status_color = TEXT_COLOR

        status_surface = self.font.render(status_text, True, status_color)
        self.screen.blit(status_surface, (sidebar_x + 20, y_offset))
        y_offset += 40

        # Player info
        if self.state == GameState.PLAYING:
            player_info = f"Playing as: {self.player_color.title()}"
            player_surface = self.small_font.render(player_info, True, TEXT_COLOR)
            self.screen.blit(player_surface, (sidebar_x + 20, y_offset))
            y_offset += 25

            turn_info = f"Current turn: {self.current_player.title()}"
            turn_color = (0, 128, 0) if self.current_player == self.player_color else (128, 0, 0)
            turn_surface = self.small_font.render(turn_info, True, turn_color)
            self.screen.blit(turn_surface, (sidebar_x + 20, y_offset))
            y_offset += 30

        # Connection status
        conn_status = "Connected" if self.connected else "Disconnected"
        conn_color = (0, 128, 0) if self.connected else (128, 0, 0)
        conn_text = self.font.render(f"Status: {conn_status}", True, conn_color)
        self.screen.blit(conn_text, (sidebar_x + 20, y_offset))
        y_offset += 40

        # Selected piece info
        if self.selected_piece and self.state == GameState.PLAYING:
            row, col = self.selected_piece
            piece = self.board[row][col]
            if piece:
                piece_info = f"Selected: {piece['type'].title()}"
                piece_surface = self.small_font.render(piece_info, True, (0, 0, 128))
                self.screen.blit(piece_surface, (sidebar_x + 20, y_offset))
                y_offset += 20

                moves_info = f"Valid moves: {len(self.valid_moves)}"
                moves_surface = self.small_font.render(moves_info, True, (0, 128, 0))
                self.screen.blit(moves_surface, (sidebar_x + 20, y_offset))
                y_offset += 30

        # Messages
        msg_title = self.font.render("Messages:", True, TEXT_COLOR)
        self.screen.blit(msg_title, (sidebar_x + 20, y_offset))
        y_offset += 30

        # Show last messages that fit
        remaining_height = WINDOW_HEIGHT - y_offset - 20
        lines_that_fit = remaining_height // 20
        start_idx = max(0, len(self.messages) - lines_that_fit)

        for i in range(start_idx, len(self.messages)):
            message = self.messages[i]
            if len(message) > 35:
                message = message[:32] + "..."

            msg_text = self.small_font.render(message, True, TEXT_COLOR)
            self.screen.blit(msg_text, (sidebar_x + 20, y_offset))
            y_offset += 20

    def draw_menu(self):
        self.screen.fill(WHITE)

        # Title
        title_text = self.title_font.render("Chess 9x9 Online", True, TEXT_COLOR)
        title_rect = title_text.get_rect(center=(WINDOW_WIDTH // 2, 100))
        self.screen.blit(title_text, title_rect)

        # Connect button
        if not self.connected:
            connect_button = pygame.Rect(WINDOW_WIDTH // 2 - 100, 200, 200, 50)
            pygame.draw.rect(self.screen, BUTTON_COLOR, connect_button)
            connect_text = self.font.render("Connect to Server", True, WHITE)
            connect_text_rect = connect_text.get_rect(center=connect_button.center)
            self.screen.blit(connect_text, connect_text_rect)

        # Join queue button
        if self.connected and self.state == GameState.MENU:
            queue_button = pygame.Rect(WINDOW_WIDTH // 2 - 100, 270, 200, 50)
            pygame.draw.rect(self.screen, BUTTON_COLOR, queue_button)
            queue_text = self.font.render("Join Game Queue", True, WHITE)
            queue_text_rect = queue_text.get_rect(center=queue_button.center)
            self.screen.blit(queue_text, queue_text_rect)

        # Instructions
        instructions = [
            "How to play:",
            "1. Connect to server",
            "2. Join the game queue",
            "3. Wait for an opponent",
            "4. Click pieces to select and move",
            "5. Valid moves are highlighted in green",
            "6. Kings in check are highlighted in red"
        ]

        y_start = 350
        for i, instruction in enumerate(instructions):
            instr_text = self.small_font.render(instruction, True, TEXT_COLOR)
            self.screen.blit(instr_text, (50, y_start + i * 25))

    def draw_waiting_screen(self):
        waiting_text = self.title_font.render("Waiting for opponent...", True, TEXT_COLOR)
        waiting_rect = waiting_text.get_rect(center=(BOARD_WIDTH // 2, BOARD_HEIGHT // 2))
        self.screen.blit(waiting_text, waiting_rect)

        # Animated dots
        dots = "." * ((pygame.time.get_ticks() // 500) % 4)
        dots_text = self.font.render(dots, True, TEXT_COLOR)
        dots_rect = dots_text.get_rect(center=(BOARD_WIDTH // 2, BOARD_HEIGHT // 2 + 50))
        self.screen.blit(dots_text, dots_rect)

    def draw_promotion_dialog(self):
        """Draw the pawn promotion dialog"""
        if not self.promotion_pending:
            return

        # Semi-transparent overlay
        overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 128))
        self.screen.blit(overlay, (0, 0))

        # Dialog box
        dialog_width = 400
        dialog_height = 200
        dialog_x = (WINDOW_WIDTH - dialog_width) // 2
        dialog_y = (WINDOW_HEIGHT - dialog_height) // 2

        pygame.draw.rect(self.screen, WHITE, (dialog_x, dialog_y, dialog_width, dialog_height))
        pygame.draw.rect(self.screen, BLACK, (dialog_x, dialog_y, dialog_width, dialog_height), 3)

        # Title
        title_text = self.font.render("Choose Promotion Piece", True, TEXT_COLOR)
        title_rect = title_text.get_rect(center=(dialog_x + dialog_width // 2, dialog_y + 30))
        self.screen.blit(title_text, title_rect)

        # Instructions
        instruction_text = self.small_font.render("Click piece or press Q/R/B/N", True, TEXT_COLOR)
        instruction_rect = instruction_text.get_rect(center=(dialog_x + dialog_width // 2, dialog_y + 50))
        self.screen.blit(instruction_text, instruction_rect)

        # Promotion options
        option_size = 60
        spacing = 80
        start_x = dialog_x + (dialog_width - (len(self.promotion_options) * spacing - 20)) // 2
        option_y = dialog_y + 90

        shortcuts = ['Q', 'R', 'B', 'N']

        for i, piece_type in enumerate(self.promotion_options):
            option_x = start_x + i * spacing

            # Draw piece sprite
            sprite = self.piece_sprites[self.player_color][piece_type]
            scaled_sprite = pygame.transform.scale(sprite, (option_size, option_size))
            sprite_rect = scaled_sprite.get_rect(center=(option_x + option_size // 2, option_y + option_size // 2))

            # Background for piece
            pygame.draw.rect(self.screen, LIGHT_BROWN, (option_x, option_y, option_size, option_size))
            pygame.draw.rect(self.screen, BLACK, (option_x, option_y, option_size, option_size), 2)

            self.screen.blit(scaled_sprite, sprite_rect)

            # Label with keyboard shortcut
            label_text = f"{piece_type.title()} ({shortcuts[i]})"
            label_surface = self.small_font.render(label_text, True, TEXT_COLOR)
            label_rect = label_surface.get_rect(center=(option_x + option_size // 2, option_y + option_size + 15))
            self.screen.blit(label_surface, label_rect)

    def draw_game_end_overlay(self):
        """Draw the game end overlay"""
        if not self.game_end_message:
            return

        # Check if timer has expired first
        current_time = pygame.time.get_ticks()
        if current_time >= self.game_end_timer:
            # Time's up, return to menu
            print("Game end timer expired, returning to menu")
            self.reset_to_menu()
            return

        # Semi-transparent overlay
        overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))

        # Main message box
        box_width = 500
        box_height = 300
        box_x = (WINDOW_WIDTH - box_width) // 2
        box_y = (WINDOW_HEIGHT - box_height) // 2

        pygame.draw.rect(self.screen, WHITE, (box_x, box_y, box_width, box_height))
        pygame.draw.rect(self.screen, BLACK, (box_x, box_y, box_width, box_height), 4)

        # Split message into lines
        lines = self.game_end_message.split('\n')

        # Draw each line
        y_start = box_y + 60
        for i, line in enumerate(lines):
            if i == 0:  # First line (result)
                text = self.large_font.render(line, True, TEXT_COLOR)
            else:
                text = self.font.render(line, True, TEXT_COLOR)

            text_rect = text.get_rect(center=(box_x + box_width // 2, y_start + i * 50))
            self.screen.blit(text, text_rect)

        # Countdown message
        remaining_time = max(0, (self.game_end_timer - current_time) / 1000)
        countdown_text = f"Returning to queue in {remaining_time:.1f}s..."
        countdown_surface = self.small_font.render(countdown_text, True, (128, 128, 128))
        countdown_rect = countdown_surface.get_rect(center=(box_x + box_width // 2, box_y + box_height - 60))
        self.screen.blit(countdown_surface, countdown_rect)

        # Click to continue hint
        hint_text = "Click anywhere or press any key to continue immediately"
        hint_surface = self.small_font.render(hint_text, True, (100, 100, 100))
        hint_rect = hint_surface.get_rect(center=(box_x + box_width // 2, box_y + box_height - 20))
        self.screen.blit(hint_surface, hint_rect)

    # Main game loop
    def run(self):
        while self.running:
            current_time = pygame.time.get_ticks()

            # Check for stuck states every 5 seconds
            if current_time - self.stuck_check_timer > 5000:
                self.stuck_check_timer = current_time
                self.check_for_stuck_state(current_time)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False

                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:  # Left click
                        if self.state == GameState.MENU:
                            self.handle_menu_click(event.pos)
                        elif self.state == GameState.PLAYING:
                            self.handle_click(event.pos)
                        elif self.state == GameState.GAME_END:
                            # Click anywhere to return to menu immediately
                            print("Game end screen clicked, returning to menu")
                            self.reset_to_menu()

                elif event.type == pygame.KEYDOWN:
                    if self.promotion_pending:
                        # Handle promotion keyboard shortcuts
                        if event.key == pygame.K_q:
                            self.handle_promotion_choice('queen')
                        elif event.key == pygame.K_r:
                            self.handle_promotion_choice('rook')
                        elif event.key == pygame.K_b:
                            self.handle_promotion_choice('bishop')
                        elif event.key == pygame.K_n:
                            self.handle_promotion_choice('knight')
                        elif event.key == pygame.K_ESCAPE:
                            self.handle_promotion_choice('queen')  # Default to queen
                    elif self.state == GameState.GAME_END:
                        # Any key press returns to menu immediately
                        print("Key pressed in game end, returning to menu")
                        self.reset_to_menu()
                    else:
                        if event.key == pygame.K_ESCAPE:
                            if self.state != GameState.MENU:
                                self.state = GameState.MENU
                                self.selected_piece = None
                                self.valid_moves = []

            # Clear screen
            self.screen.fill(WHITE)

            # Draw based on current state
            if self.state == GameState.MENU:
                self.draw_menu()
            elif self.state == GameState.WAITING:
                self.draw_waiting_screen()
                self.draw_sidebar()
            elif self.state == GameState.PLAYING:
                # Safety check: if not connected or no game_id, return to menu
                if not self.connected or not self.game_id:
                    print("Safety check: Not connected or no game_id, returning to menu")
                    self.reset_to_menu()
                else:
                    self.draw_board()
                    self.draw_sidebar()
            elif self.state == GameState.GAME_END:
                self.draw_board()
                self.draw_sidebar()
                self.draw_game_end_overlay()
            else:
                # Unknown state, reset to menu
                print(f"Unknown state: {self.state}, resetting to menu")
                self.reset_to_menu()

            # Draw promotion dialog on top if needed
            if self.promotion_pending:
                self.draw_promotion_dialog()

            pygame.display.flip()
            self.clock.tick(60)

        # Cleanup
        if self.connected:
            self.socket.close()
        pygame.quit()


    def check_for_stuck_state(self, current_time):
        """Check if the client is stuck and needs to be reset"""
        # If in playing state but no moves for 30 seconds, something might be wrong
        if (self.state == GameState.PLAYING and
                self.last_move_time > 0 and
                current_time - self.last_move_time > 30000):  # 30 seconds

            print("WARNING: No moves for 30 seconds, checking connection...")
            if not self.connected:
                print("Connection lost, returning to menu")
                self.reset_to_menu()

        # If game has been in an unusual state for too long, reset
        if (self.state not in [GameState.MENU, GameState.WAITING, GameState.PLAYING, GameState.GAME_END]):
            print(f"WARNING: Invalid state {self.state}, resetting to menu")
            self.reset_to_menu()


if __name__ == "__main__":
    client = ChessClient()
    try:
        client.run()
    except KeyboardInterrupt:
        print("\nClient shutting down...")
    except Exception as e:
        print(f"Client error: {e}")
    finally:
        if client.connected:
            client.socket.close()
        pygame.quit()
        sys.exit()
