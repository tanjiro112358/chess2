import socket
import threading
import json
import pickle
import hashlib
import secrets
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding, hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.asymmetric import dh
from cryptography.hazmat.primitives.asymmetric.dh import DHParameterNumbers, DHParameters, DHPublicNumbers
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
import os
import time
import random


class ChessServer:
    def __init__(self, host='10.100.102.43', port=8888):
        self.host = host
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # Game state
        self.games = {}  # game_id: Game object
        self.waiting_players = []  # List of waiting players
        self.clients = {}  # client_socket: player_info

        # Database
        self.db_file = 'users.pkl'
        self.users = self.load_users()

        # Email config (configure these for password reset)
        self.smtp_server = "smtp.gmail.com"
        self.smtp_port = 587
        self.email_user = "your_email@gmail.com"
        self.email_password = "your_app_password"

        # Security
        self.pepper = b"chess_game_pepper_2024_change_this_in_production"
        self.reset_codes = {}  # email: (code, timestamp)

        # DH parameters for key exchange (using standard RFC 3526 group)
        self.dh_params = None
        self._initialize_dh_params()

    def _initialize_dh_params(self):
        """Initialize DH parameters using RFC 3526 Group 14 (2048-bit)"""
        # Using well-known safe prime from RFC 3526
        p = int(
            "FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD1"
            "29024E088A67CC74020BBEA63B139B22514A08798E3404DD"
            "EF9519B3CD3A431B302B0A6DF25F14374FE1356D6D51C245"
            "E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7ED"
            "EE386BFB5A899FA5AE9F24117C4B1FE649286651ECE45B3D"
            "C2007CB8A163BF0598DA48361C55D39A69163FA8FD24CF5F"
            "83655D23DCA3AD961C62F356208552BB9ED529077096966D"
            "670C354E4ABC9804F1746C08CA18217C32905E462E36CE3B"
            "E39E772C180E86039B2783A2EC07A28FB5C55DF06F4C52C9"
            "DE2BCBF6955817183995497CEA956AE515D2261898FA0510"
            "15728E5A8AACAA68FFFFFFFFFFFFFFFF", 16
        )
        g = 2

        param_numbers = DHParameterNumbers(p, g)
        self.dh_params = param_numbers.parameters()

    def load_users(self):
        """Load user database from pickle file"""
        try:
            with open(self.db_file, 'rb') as f:
                return pickle.load(f)
        except FileNotFoundError:
            return {}

    def save_users(self):
        """Save user database to pickle file"""
        with open(self.db_file, 'wb') as f:
            pickle.dump(self.users, f)

    def hash_password(self, password, salt):
        """Hash password with salt and pepper"""
        return hashlib.pbkdf2_hmac('sha256',
                                   password.encode() + self.pepper,
                                   salt, 100000)

    def generate_reset_code(self):
        """Generate 6-digit reset code"""
        return str(random.randint(100000, 999999))

    def send_reset_email(self, email, code):
        """Send password reset email"""
        try:
            msg = MIMEMultipart()
            msg['From'] = self.email_user
            msg['To'] = email
            msg['Subject'] = "Chess Game Password Reset"

            body = f"Your password reset code is: {code}\nThis code expires in 10 minutes."
            msg.attach(MIMEText(body, 'plain'))

            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()
            server.login(self.email_user, self.email_password)
            server.send_message(msg)
            server.quit()
            return True
        except Exception as e:
            print(f"Email error: {e}")
            return False

    def generate_aes_key(self, shared_secret):
        """Generate AES key from DH shared secret"""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b'chess_salt',
            iterations=100000,
        )
        return kdf.derive(shared_secret)

    def encrypt_message(self, message, key):
        """Encrypt message using AES-CBC"""
        iv = os.urandom(16)
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
        encryptor = cipher.encryptor()

        # Pad message
        padder = padding.PKCS7(128).padder()
        padded_data = padder.update(message.encode()) + padder.finalize()

        encrypted = encryptor.update(padded_data) + encryptor.finalize()
        return iv + encrypted

    def decrypt_message(self, encrypted_data, key):
        """Decrypt message using AES-CBC"""
        iv = encrypted_data[:16]
        encrypted = encrypted_data[16:]

        cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
        decryptor = cipher.decryptor()

        padded_data = decryptor.update(encrypted) + decryptor.finalize()

        # Unpad message
        unpadder = padding.PKCS7(128).unpadder()
        data = unpadder.update(padded_data) + unpadder.finalize()

        return data.decode()

    def start_server(self):
        """Start the chess server"""
        self.socket.bind((self.host, self.port))
        self.socket.listen(5)
        print(f"Chess server listening on {self.host}:{self.port}")
        print("Features: User accounts, email reset, encryption, full chess rules")

        while True:
            try:
                client_socket, address = self.socket.accept()
                print(f"Connection from {address}")

                client_thread = threading.Thread(
                    target=self.handle_client,
                    args=(client_socket, address)
                )
                client_thread.daemon = True
                client_thread.start()
            except Exception as e:
                print(f"Error accepting connection: {e}")

    def handle_client(self, client_socket, address):
        """Handle individual client connection"""
        try:
            print(f"Starting key exchange with {address}")

            # Generate server keypair
            private_key = self.dh_params.generate_private_key()
            public_key = private_key.public_key()

            # Get public key numbers for transmission
            public_numbers = public_key.public_numbers()

            # Send server's public key as raw numbers
            server_public_data = {
                'y': public_numbers.y,
                'p': public_numbers.parameter_numbers.p,
                'g': public_numbers.parameter_numbers.g
            }

            server_data_json = json.dumps(server_public_data)
            server_data_bytes = server_data_json.encode('utf-8')

            client_socket.send(len(server_data_bytes).to_bytes(4, 'big'))
            client_socket.send(server_data_bytes)

            # Receive client's public key
            client_data_len = int.from_bytes(client_socket.recv(4), 'big')
            client_data_bytes = b''
            while len(client_data_bytes) < client_data_len:
                chunk = client_socket.recv(client_data_len - len(client_data_bytes))
                if not chunk:
                    raise ConnectionError("Client disconnected during key exchange")
                client_data_bytes += chunk

            client_data_json = client_data_bytes.decode('utf-8')
            client_public_data = json.loads(client_data_json)

            # Reconstruct client's public key
            client_param_numbers = DHParameterNumbers(
                client_public_data['p'],
                client_public_data['g']
            )
            client_public_numbers = DHPublicNumbers(
                client_public_data['y'],
                client_param_numbers
            )
            client_public_key = client_public_numbers.public_key()

            # Calculate shared secret
            shared_secret = private_key.exchange(client_public_key)
            print(f"Key exchange successful with {address}")

            # Generate AES key
            aes_key = self.generate_aes_key(shared_secret)

            # Store client info
            self.clients[client_socket] = {
                'address': address,
                'aes_key': aes_key,
                'username': None,
                'game_id': None
            }

            while True:
                # Receive encrypted message
                msg_len = int.from_bytes(client_socket.recv(4), 'big')
                if msg_len == 0:
                    break

                encrypted_data = client_socket.recv(msg_len)
                decrypted_msg = self.decrypt_message(encrypted_data, aes_key)

                message = json.loads(decrypted_msg)
                response = self.process_message(client_socket, message)

                if response:
                    self.send_encrypted_response(client_socket, response)

        except Exception as e:
            print(f"Error handling client {address}: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.cleanup_client(client_socket)

    def send_encrypted_response(self, client_socket, response):
        """Send encrypted response to client"""
        try:
            if client_socket not in self.clients:
                print(f"Error: Client socket not in clients list!")
                return False

            aes_key = self.clients[client_socket]['aes_key']
            encrypted_response = self.encrypt_message(json.dumps(response), aes_key)

            client_socket.send(len(encrypted_response).to_bytes(4, 'big'))
            client_socket.send(encrypted_response)
            return True
        except Exception as e:
            print(f"Error sending response: {e}")
            return False

    def process_message(self, client_socket, message):
        """Process incoming message from client"""
        msg_type = message.get('type')

        if msg_type == 'register':
            return self.handle_register(client_socket, message)
        elif msg_type == 'login':
            return self.handle_login(client_socket, message)
        elif msg_type == 'request_reset':
            return self.handle_request_reset(message)
        elif msg_type == 'reset_password':
            return self.handle_reset_password(message)
        elif msg_type == 'join_queue':
            return self.handle_join_queue(client_socket)
        elif msg_type == 'leave_queue':
            return self.handle_leave_queue(client_socket)
        elif msg_type == 'move':
            return self.handle_move(client_socket, message)
        elif msg_type == 'resign':
            return self.handle_resign(client_socket)
        else:
            return {'type': 'error', 'message': 'Unknown message type'}

    def handle_register(self, client_socket, message):
        """Handle user registration"""
        username = message.get('username')
        password = message.get('password')
        email = message.get('email')

        if not username or not password or not email:
            return {'type': 'register_response', 'success': False, 'message': 'Missing fields'}

        if username in self.users:
            return {'type': 'register_response', 'success': False, 'message': 'Username already exists'}

        # Generate salt and hash password
        salt = secrets.token_bytes(32)
        password_hash = self.hash_password(password, salt)

        # Store user
        self.users[username] = {
            'password_hash': password_hash,
            'salt': salt,
            'email': email,
            'games_played': 0,
            'wins': 0,
            'losses': 0,
            'draws': 0,
            'rating': 1200,
            'created_at': time.time()
        }

        self.save_users()
        print(f"New user registered: {username}")
        return {'type': 'register_response', 'success': True, 'message': 'Registration successful'}

    def handle_login(self, client_socket, message):
        """Handle user login"""
        username = message.get('username')
        password = message.get('password')

        if not username or not password:
            return {'type': 'login_response', 'success': False, 'message': 'Missing credentials'}

        if username not in self.users:
            return {'type': 'login_response', 'success': False, 'message': 'Invalid credentials'}

        user_data = self.users[username]
        password_hash = self.hash_password(password, user_data['salt'])

        if password_hash != user_data['password_hash']:
            return {'type': 'login_response', 'success': False, 'message': 'Invalid credentials'}

        # Update client info
        self.clients[client_socket]['username'] = username

        print(f"User logged in: {username}")
        return {
            'type': 'login_response',
            'success': True,
            'username': username,
            'stats': {
                'games_played': user_data['games_played'],
                'wins': user_data['wins'],
                'losses': user_data['losses'],
                'draws': user_data['draws'],
                'rating': user_data['rating']
            }
        }

    def handle_request_reset(self, message):
        """Handle password reset request"""
        email = message.get('email')

        # Find user by email
        user_found = False
        for username, user_data in self.users.items():
            if user_data['email'] == email:
                user_found = True
                break

        if not user_found:
            return {'type': 'reset_response', 'success': False, 'message': 'Email not found'}

        # Generate and send reset code
        code = self.generate_reset_code()
        self.reset_codes[email] = (code, time.time())

        if self.send_reset_email(email, code):
            print(f"Reset code sent to {email}")
            return {'type': 'reset_response', 'success': True, 'message': 'Reset code sent to email'}
        else:
            return {'type': 'reset_response', 'success': False, 'message': 'Failed to send email'}

    def handle_reset_password(self, message):
        """Handle password reset with code"""
        email = message.get('email')
        code = message.get('code')
        new_password = message.get('new_password')

        if email not in self.reset_codes:
            return {'type': 'reset_password_response', 'success': False, 'message': 'Invalid reset code'}

        stored_code, timestamp = self.reset_codes[email]

        # Check if code is expired (10 minutes)
        if time.time() - timestamp > 600:
            del self.reset_codes[email]
            return {'type': 'reset_password_response', 'success': False, 'message': 'Reset code expired'}

        if code != stored_code:
            return {'type': 'reset_password_response', 'success': False, 'message': 'Invalid reset code'}

        # Find and update user password
        for username, user_data in self.users.items():
            if user_data['email'] == email:
                salt = secrets.token_bytes(32)
                password_hash = self.hash_password(new_password, salt)
                user_data['password_hash'] = password_hash
                user_data['salt'] = salt
                break

        # Clean up reset code
        del self.reset_codes[email]
        self.save_users()

        print(f"Password reset successful for {email}")
        return {'type': 'reset_password_response', 'success': True, 'message': 'Password reset successful'}

    def handle_join_queue(self, client_socket):
        """Handle player joining matchmaking queue"""
        username = self.clients[client_socket]['username']

        if not username:
            return {'type': 'queue_response', 'success': False, 'message': 'Not logged in'}

        if client_socket not in self.waiting_players:
            self.waiting_players.append(client_socket)
            print(f"{username} joined queue")

        # Try to match players
        if len(self.waiting_players) >= 2:
            player1 = self.waiting_players.pop(0)
            player2 = self.waiting_players.pop(0)

            game_id = self.create_game(player1, player2)

            # Notify both players
            self.send_encrypted_response(player1, {
                'type': 'game_start',
                'game_id': game_id,
                'color': 'white',
                'opponent': self.clients[player2]['username']
            })

            self.send_encrypted_response(player2, {
                'type': 'game_start',
                'game_id': game_id,
                'color': 'black',
                'opponent': self.clients[player1]['username']
            })

        return {'type': 'queue_response', 'success': True, 'message': 'Joined queue'}

    def handle_leave_queue(self, client_socket):
        """Handle player leaving matchmaking queue"""
        if client_socket in self.waiting_players:
            self.waiting_players.remove(client_socket)
            username = self.clients[client_socket]['username']
            print(f"{username} left queue")

        return {'type': 'queue_response', 'success': True, 'message': 'Left queue'}

    def create_game(self, player1, player2):
        """Create a new chess game"""
        game_id = secrets.token_hex(8)
        game = ChessGame(game_id, player1, player2)

        self.games[game_id] = game
        self.clients[player1]['game_id'] = game_id
        self.clients[player2]['game_id'] = game_id

        print(f"Game {game_id} created: {self.clients[player1]['username']} vs {self.clients[player2]['username']}")
        return game_id

    def handle_move(self, client_socket, message):
        """Handle chess move"""
        game_id = self.clients[client_socket]['game_id']

        if not game_id or game_id not in self.games:
            return {'type': 'move_response', 'success': False, 'message': 'No active game'}

        game = self.games[game_id]
        from_pos = message.get('from')
        to_pos = message.get('to')

        result = game.make_move(client_socket, from_pos, to_pos)

        if result['success']:
            game_status = result.get('game_status', 'continue')

            # Handle game end conditions
            if game_status in ['checkmate', 'stalemate']:
                self.handle_game_end(client_socket, game_id, game_status)
                return {'type': 'move_response', 'success': True, 'game_over': True, 'reason': game_status}
            else:
                # Normal move, notify opponent
                opponent = game.get_opponent(client_socket)
                if opponent:
                    opponent_message = {
                        'type': 'opponent_move',
                        'from': from_pos,
                        'to': to_pos,
                        'board': game.get_board_state(),
                        'turn': result['turn'],
                        'in_check': result.get('in_check', False)
                    }

                    self.send_encrypted_response(opponent, opponent_message)

        return result

    def handle_game_end(self, triggering_player, game_id, reason):
        """Handle game end scenarios"""
        game = self.games[game_id]
        player1 = game.white_player
        player2 = game.black_player

        player1_username = self.clients[player1]['username']
        player2_username = self.clients[player2]['username']

        if reason == 'checkmate':
            # The player who made the move wins
            winner = triggering_player
            loser = game.get_opponent(triggering_player)

            # Update stats
            winner_username = self.clients[winner]['username']
            loser_username = self.clients[loser]['username']

            self.users[winner_username]['wins'] += 1
            self.users[winner_username]['games_played'] += 1
            self.users[loser_username]['losses'] += 1
            self.users[loser_username]['games_played'] += 1

            # Notify players
            self.send_encrypted_response(winner, {
                'type': 'game_end',
                'result': 'win',
                'reason': 'checkmate'
            })

            self.send_encrypted_response(loser, {
                'type': 'game_end',
                'result': 'loss',
                'reason': 'checkmate'
            })

            print(f"Game {game_id} ended: {winner_username} wins by checkmate")

        elif reason == 'stalemate':
            # Draw
            self.users[player1_username]['draws'] += 1
            self.users[player1_username]['games_played'] += 1
            self.users[player2_username]['draws'] += 1
            self.users[player2_username]['games_played'] += 1

            # Notify both players
            for player in [player1, player2]:
                self.send_encrypted_response(player, {
                    'type': 'game_end',
                    'result': 'draw',
                    'reason': 'stalemate'
                })

            print(f"Game {game_id} ended: stalemate")

        # Clean up game
        del self.games[game_id]
        self.clients[player1]['game_id'] = None
        self.clients[player2]['game_id'] = None
        self.save_users()

    def handle_resign(self, client_socket):
        """Handle player resignation"""
        game_id = self.clients[client_socket]['game_id']

        if not game_id or game_id not in self.games:
            return None

        game = self.games[game_id]
        resigning_player_username = self.clients[client_socket]['username']

        # Find opponent
        opponent = game.get_opponent(client_socket)
        if not opponent:
            return None

        winner_username = self.clients[opponent]['username']

        # Update stats
        self.users[winner_username]['wins'] += 1
        self.users[winner_username]['games_played'] += 1
        self.users[resigning_player_username]['losses'] += 1
        self.users[resigning_player_username]['games_played'] += 1

        # Notify opponent they won
        self.send_encrypted_response(opponent, {
            'type': 'game_end',
            'result': 'win',
            'reason': 'opponent_resigned'
        })

        # Clean up game
        del self.games[game_id]
        self.clients[client_socket]['game_id'] = None
        self.clients[opponent]['game_id'] = None

        self.save_users()
        print(f"Game {game_id}: {resigning_player_username} resigned, {winner_username} wins")

        return None  # No response to resigning player needed

    def cleanup_client(self, client_socket):
        """Clean up client connection"""
        if client_socket in self.clients:
            game_id = self.clients[client_socket]['game_id']
            username = self.clients[client_socket].get('username', 'Unknown')
            print(f"{username} disconnected")

            # Handle game cleanup
            if game_id and game_id in self.games:
                game = self.games[game_id]
                opponent = game.get_opponent(client_socket)

                if opponent:
                    # Update stats - opponent wins by disconnect
                    if username != 'Unknown':
                        opponent_username = self.clients[opponent]['username']
                        self.users[opponent_username]['wins'] += 1
                        self.users[opponent_username]['games_played'] += 1
                        self.users[username]['losses'] += 1
                        self.users[username]['games_played'] += 1
                        self.save_users()

                    self.send_encrypted_response(opponent, {
                        'type': 'game_end',
                        'result': 'win',
                        'reason': 'opponent_disconnected'
                    })
                    self.clients[opponent]['game_id'] = None

                del self.games[game_id]

            # Remove from waiting queue
            if client_socket in self.waiting_players:
                self.waiting_players.remove(client_socket)

            del self.clients[client_socket]

        try:
            client_socket.close()
        except:
            pass


class ChessGame:
    """Complete chess game with full rules including check/checkmate"""

    def __init__(self, game_id, player1, player2):
        self.game_id = game_id
        self.white_player = player1
        self.black_player = player2
        self.current_turn = 'white'
        self.board = self.initialize_board()
        self.move_history = []
        self.game_over = False

    def initialize_board(self):
        """Initialize 9x9 chess board with 2 queens"""
        board = [[None for _ in range(9)] for _ in range(9)]

        # Place white pieces
        board[8][0] = 'white_rook'
        board[8][1] = 'white_knight'
        board[8][2] = 'white_bishop'
        board[8][3] = 'white_queen'
        board[8][4] = 'white_king'
        board[8][5] = 'white_queen'  # Second queen
        board[8][6] = 'white_bishop'
        board[8][7] = 'white_knight'
        board[8][8] = 'white_rook'

        # White pawns
        for i in range(9):
            board[7][i] = 'white_pawn'

        # Place black pieces
        board[0][0] = 'black_rook'
        board[0][1] = 'black_knight'
        board[0][2] = 'black_bishop'
        board[0][3] = 'black_queen'
        board[0][4] = 'black_king'
        board[0][5] = 'black_queen'  # Second queen
        board[0][6] = 'black_bishop'
        board[0][7] = 'black_knight'
        board[0][8] = 'black_rook'

        # Black pawns
        for i in range(9):
            board[1][i] = 'black_pawn'

        return board

    def get_board_state(self):
        """Get current board state"""
        return self.board

    def get_opponent(self, player):
        """Get opponent player"""
        if player == self.white_player:
            return self.black_player
        elif player == self.black_player:
            return self.white_player
        return None

    def find_king_position(self, color):
        """Find the position of the king for the given color"""
        for row in range(9):
            for col in range(9):
                piece = self.board[row][col]
                if piece == f'{color}_king':
                    return (row, col)
        return None

    def is_square_attacked(self, pos, by_color):
        """Check if a square is attacked by pieces of the given color"""
        for row in range(9):
            for col in range(9):
                piece = self.board[row][col]
                if piece and piece.startswith(by_color):
                    if self.can_piece_attack(piece, (row, col), pos):
                        return True
        return False

    def can_piece_attack(self, piece, from_pos, to_pos):
        """Check if a piece can attack a target square"""
        piece_type = piece.split('_')[1]
        piece_color = piece.split('_')[0]
        from_row, from_col = from_pos
        to_row, to_col = to_pos

        if not (0 <= to_row < 9 and 0 <= to_col < 9):
            return False

        if piece_type == 'pawn':
            direction = -1 if piece_color == 'white' else 1
            return (abs(from_col - to_col) == 1 and to_row == from_row + direction)

        elif piece_type == 'rook':
            if from_row != to_row and from_col != to_col:
                return False
            return self.is_path_clear(from_pos, to_pos)

        elif piece_type == 'knight':
            row_diff = abs(from_row - to_row)
            col_diff = abs(from_col - to_col)
            return (row_diff == 2 and col_diff == 1) or (row_diff == 1 and col_diff == 2)

        elif piece_type == 'bishop':
            if abs(from_row - to_row) != abs(from_col - to_col):
                return False
            return self.is_path_clear(from_pos, to_pos)

        elif piece_type == 'queen':
            is_rook_move = (from_row == to_row or from_col == to_col)
            is_bishop_move = (abs(from_row - to_row) == abs(from_col - to_col))
            if not (is_rook_move or is_bishop_move):
                return False
            return self.is_path_clear(from_pos, to_pos)

        elif piece_type == 'king':
            return (abs(from_row - to_row) <= 1 and
                    abs(from_col - to_col) <= 1 and
                    (from_row != to_row or from_col != to_col))

        return False

    def is_in_check(self, color):
        """Check if the king of the given color is in check"""
        king_pos = self.find_king_position(color)
        if not king_pos:
            return False

        enemy_color = 'black' if color == 'white' else 'white'
        return self.is_square_attacked(king_pos, enemy_color)

    def is_path_clear(self, from_pos, to_pos):
        """Check if path between positions is clear"""
        from_row, from_col = from_pos
        to_row, to_col = to_pos

        row_step = 0 if from_row == to_row else (1 if to_row > from_row else -1)
        col_step = 0 if from_col == to_col else (1 if to_col > from_col else -1)

        current_row, current_col = from_row + row_step, from_col + col_step

        while current_row != to_row or current_col != to_col:
            if self.board[current_row][current_col] is not None:
                return False
            current_row += row_step
            current_col += col_step

        return True

    def is_legal_move(self, from_pos, to_pos, color):
        """Check if a move is legal (doesn't leave own king in check)"""
        from_row, from_col = from_pos
        to_row, to_col = to_pos

        # Make the move temporarily
        moving_piece = self.board[from_row][from_col]
        captured_piece = self.board[to_row][to_col]

        self.board[to_row][to_col] = moving_piece
        self.board[from_row][from_col] = None

        # Check if this leaves the king in check
        in_check = self.is_in_check(color)

        # Restore the board
        self.board[from_row][from_col] = moving_piece
        self.board[to_row][to_col] = captured_piece

        return not in_check

    def get_all_legal_moves(self, color):
        """Get all legal moves for a color"""
        legal_moves = []

        for row in range(9):
            for col in range(9):
                piece = self.board[row][col]
                if piece and piece.startswith(color):
                    for dest_row in range(9):
                        for dest_col in range(9):
                            from_pos = (row, col)
                            to_pos = (dest_row, dest_col)

                            if from_pos == to_pos:
                                continue

                            if self.is_valid_piece_move(from_pos, to_pos, piece, color):
                                if self.is_legal_move(from_pos, to_pos, color):
                                    legal_moves.append((from_pos, to_pos))

        return legal_moves

    def is_checkmate(self, color):
        """Check if the given color is in checkmate"""
        if not self.is_in_check(color):
            return False

        legal_moves = self.get_all_legal_moves(color)
        return len(legal_moves) == 0

    def is_stalemate(self, color):
        """Check if the given color is in stalemate"""
        if self.is_in_check(color):
            return False

        legal_moves = self.get_all_legal_moves(color)
        return len(legal_moves) == 0

    def is_valid_piece_move(self, from_pos, to_pos, piece, player_color):
        """Check if piece can move (basic rules, no check consideration)"""
        from_row, from_col = from_pos
        to_row, to_col = to_pos

        # Basic bounds checking
        if not (0 <= to_row < 9 and 0 <= to_col < 9):
            return False

        # Can't capture own piece
        target_piece = self.board[to_row][to_col]
        if target_piece and target_piece.startswith(player_color):
            return False

        piece_type = piece.split('_')[1]

        if piece_type == 'pawn':
            return self.validate_pawn_move(from_pos, to_pos, player_color)
        elif piece_type == 'rook':
            return self.validate_rook_move(from_pos, to_pos)
        elif piece_type == 'knight':
            return self.validate_knight_move(from_pos, to_pos)
        elif piece_type == 'bishop':
            return self.validate_bishop_move(from_pos, to_pos)
        elif piece_type == 'queen':
            return self.validate_queen_move(from_pos, to_pos)
        elif piece_type == 'king':
            return self.validate_king_move(from_pos, to_pos)

        return False

    def validate_pawn_move(self, from_pos, to_pos, color):
        """Validate pawn movement"""
        from_row, from_col = from_pos
        to_row, to_col = to_pos

        direction = -1 if color == 'white' else 1

        # Forward move
        if from_col == to_col:
            if to_row == from_row + direction:
                return self.board[to_row][to_col] is None
            elif to_row == from_row + 2 * direction:
                # Double move from starting position
                start_row = 7 if color == 'white' else 1
                return (from_row == start_row and
                        self.board[to_row][to_col] is None and
                        self.board[from_row + direction][to_col] is None)

        # Diagonal capture
        elif abs(from_col - to_col) == 1 and to_row == from_row + direction:
            return (self.board[to_row][to_col] is not None and
                    not self.board[to_row][to_col].startswith(color))

        return False

    def validate_rook_move(self, from_pos, to_pos):
        """Validate rook movement"""
        from_row, from_col = from_pos
        to_row, to_col = to_pos

        if from_row != to_row and from_col != to_col:
            return False

        return self.is_path_clear(from_pos, to_pos)

    def validate_knight_move(self, from_pos, to_pos):
        """Validate knight movement"""
        from_row, from_col = from_pos
        to_row, to_col = to_pos

        row_diff = abs(from_row - to_row)
        col_diff = abs(from_col - to_col)

        return (row_diff == 2 and col_diff == 1) or (row_diff == 1 and col_diff == 2)

    def validate_bishop_move(self, from_pos, to_pos):
        """Validate bishop movement"""
        from_row, from_col = from_pos
        to_row, to_col = to_pos

        if abs(from_row - to_row) != abs(from_col - to_col):
            return False

        return self.is_path_clear(from_pos, to_pos)

    def validate_queen_move(self, from_pos, to_pos):
        """Validate queen movement"""
        return (self.validate_rook_move(from_pos, to_pos) or
                self.validate_bishop_move(from_pos, to_pos))

    def validate_king_move(self, from_pos, to_pos):
        """Validate king movement"""
        from_row, from_col = from_pos
        to_row, to_col = to_pos

        return (abs(from_row - to_row) <= 1 and
                abs(from_col - to_col) <= 1 and
                (from_row != to_row or from_col != to_col))

    def make_move(self, player, from_pos, to_pos):
        """Make a chess move with full rule validation"""
        if self.game_over:
            return {'success': False, 'message': 'Game is over'}

        player_color = 'white' if player == self.white_player else 'black'

        if player_color != self.current_turn:
            return {'success': False, 'message': 'Not your turn'}

        from_row, from_col = from_pos
        to_row, to_col = to_pos

        piece = self.board[from_row][from_col]

        if not piece or not piece.startswith(player_color):
            return {'success': False, 'message': 'Invalid piece selection'}

        # Validate move
        if not self.is_valid_piece_move(from_pos, to_pos, piece, player_color):
            return {'success': False, 'message': 'Invalid move'}

        # Check if move leaves own king in check
        if not self.is_legal_move(from_pos, to_pos, player_color):
            return {'success': False, 'message': 'Move leaves king in check'}

        # Make the move
        captured_piece = self.board[to_row][to_col]
        self.board[to_row][to_col] = piece
        self.board[from_row][from_col] = None

        # Record move
        self.move_history.append({
            'from': from_pos,
            'to': to_pos,
            'piece': piece,
            'captured': captured_piece
        })

        # Switch turns
        opponent_color = 'black' if self.current_turn == 'white' else 'white'
        self.current_turn = opponent_color

        # Check for game end conditions
        game_status = 'continue'

        if self.is_in_check(opponent_color):
            if self.is_checkmate(opponent_color):
                self.game_over = True
                game_status = 'checkmate'
            else:
                game_status = 'check'
        elif self.is_stalemate(opponent_color):
            self.game_over = True
            game_status = 'stalemate'

        return {
            'success': True,
            'board': self.board,
            'captured': captured_piece,
            'turn': self.current_turn,
            'game_status': game_status,
            'in_check': self.is_in_check(opponent_color) if game_status != 'checkmate' else False
        }


if __name__ == "__main__":
    server = ChessServer()
    server.start_server()