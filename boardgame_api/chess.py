import PIL.Image
import itertools
import string
import random
import subprocess
import io
import os.path

IDSAMPLE = string.ascii_uppercase + string.ascii_lowercase + string.digits + '-+'
MODES = [{'text': 'Против ИИ', 'code': 'AI'}, {'text': 'Обычная игра', 'code': 'QUICK'}]
FENSYMBOLS = {'k': 'King',
              'q': 'Queen',
              'r': 'Rook',
              'b': 'Bishop',
              'n': 'Knight',
              'p': 'Pawn'}
IMAGES = {}
for name in ['Pawn', 'King', 'Bishop', 'Rook', 'Queen', 'Knight']:
    IMAGES[name] = [PIL.Image.open(f'images/chess/{color}_{name.lower()}.png') for color in ['black', 'white']]
STARTPOS = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'
#rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR -> rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR

def _fentoimagemap(fen):
    res = {}
    fen = fen[:fen.find(' ')].split('/')
    for line in range(8):
        offset = 0
        for column in range(8):
            if column + offset > 7:
                break
            char = fen[line][column]
            if char.isdigit():
                offset += int(char) - 1
            else:
                res[(column + offset, 7 - line)] = IMAGES[FENSYMBOLS[char.lower()]][char.isupper()]
    
    return res

def _imgpos(pos):
    return [19 + 60 * pos[0] - pos[0] // 2, 422 - 59 * pos[1]]

def decode_pos(pos):
    return [ord(pos[0]) - 97, int(pos[1]) - 1]

def encode_pos(pos):
    return chr(pos[0] + 97) + str(pos[1] + 1)

def in_bounds(pos):
    return 0 <= pos[0] <= 7 and 0 <= pos[1] <= 7

class BaseFigure():
    name = 'PLACEHOLDER'
    fen_symbol = ['none', 'NONE']
    def __init__(self, pos, match, is_white):
        self.image = IMAGES[type(self).__name__][int(is_white)]
        self.pos = pos
        self.is_white = is_white
        self.match = match
        self.moved = False
        self.fen_symbol = self.fen_symbol[int(is_white)]
        
    def __str__(self):
        return f"{self.name} на {encode_pos(self.pos)}"
        
    def get_moves(self):
        return []
    
    def move(self, pos):
        print(self.match.id, '::', self.match.get_context()['player'].name, ':', encode_pos(self.pos)+encode_pos(pos))
        if pos == self.match.enpassant_pos[1]:
            figure = self.match[self.match.enpassant_pos[0]]
            del self.match[self.match.enpassant_pos[0]]
        else:
            figure = self.match[pos]
            if figure:
                del self.match[pos]
        
        self.pos = pos
        self.match.enpassant_pos = [None, None]
        self.moved = True
        return figure
        
    def is_legal(self, move_pos):
        if not in_bounds(move_pos):
            return False
        
        actual_pos = self.pos
        allied_king = self.match.get_king(self.is_white)
        killed = self.match[move_pos]
        if killed:
            del self.match[move_pos]
        self.pos = move_pos
        
        res = allied_king.in_check()
        
        self.pos = actual_pos
        if killed:
            self.match[move_pos] = killed
        return not res
        
    
class Pawn(BaseFigure):
    name = 'Пешка'
    fen_symbol = ['p', 'P']
    def get_moves(self):
        allies, enemies = (self.match.whites, self.match.blacks) if self.is_white else (self.match.blacks, self.match.whites)
        positions = []
        direction = 1 if self.is_white else -1
        if [self.pos[0], self.pos[1] + direction] not in [i.pos for i in enemies + allies]:
            positions.append([self.pos[0], self.pos[1] + direction])
            if not self.moved and [self.pos[0], self.pos[1] + direction * 2] not in [i.pos for i in enemies]:
                positions.append([self.pos[0], self.pos[1] + direction * 2])
            
        if [self.pos[0] + 1, self.pos[1] + direction] in [i.pos for i in enemies] + [self.match.enpassant_pos[1]]:
            positions.append([self.pos[0] + 1, self.pos[1] + direction])
            
        if [self.pos[0] - 1, self.pos[1] + direction] in [i.pos for i in enemies] + [self.match.enpassant_pos[1]]:
            positions.append([self.pos[0] - 1, self.pos[1] + direction])
        
        moves = []
        for move in positions:
            if in_bounds(move) and move not in [i.pos for i in allies]:
                moves.append({'pos': move, 'killing': move in [i.pos for i in enemies] + [self.match.enpassant_pos[1]]})
                
        return moves
    
    def move(self, pos):
        old_pos = self.pos
        killed = super().move(pos)
        if abs(old_pos[1] - pos[1]) == 2:
            self.match.enpassant_pos = [pos, [pos[0], (pos[1] + old_pos[1]) // 2]]
            
        return killed
                
class Knight(BaseFigure):
    name = 'Конь'
    fen_symbol = ['n', 'N']
    def get_moves(self):
        allies, enemies = (self.match.whites, self.match.blacks) if self.is_white else (self.match.blacks, self.match.whites)
        moves = []
        for move in [[2, -1], [2, 1], [1, 2], [1, -2], [-1, 2], [-1, -2], [-2, 1], [-2, -1]]:
            move = [a+b for a,b in zip(move, self.pos)]
            if in_bounds(move) and move not in [i.pos for i in allies]:
                moves.append({'pos': move, 'killing': move in [i.pos for i in enemies] + [self.match.enpassant_pos[1]]})
                
        return moves
    
class Rook(BaseFigure):
    name = 'Ладья'
    fen_symbol = ['r', 'R']
    def get_moves(self):
        allies, enemies = (self.match.whites, self.match.blacks) if self.is_white else (self.match.blacks, self.match.whites)
        moves = []
        for move_seq in [zip(range(1, 8), [0]*7), zip(range(-1, -8, -1), [0]*7),
                         zip([0]*7, range(1, 8)), zip([0]*7, range(-1, -8, -1))]:
            for move in move_seq:
                move = [a + b for a, b in zip(self.pos, move)]
                if move in [i.pos for i in allies] or not in_bounds(move):
                    break
                elif move in [i.pos for i in enemies] + [self.match.enpassant_pos[1]]:
                    moves.append({'pos': move, 'killing': True})
                    break
                else:
                    moves.append({'pos': move, 'killing': False})
                    
        return moves
    
class Bishop(BaseFigure):
    name = 'Слон'
    fen_symbol = ['b', 'B']
    def get_moves(self):
        allies, enemies = (self.match.whites, self.match.blacks) if self.is_white else (self.match.blacks, self.match.whites)
        moves = []
        for move_seq in [zip(range(1, 8), range(1, 8)), zip(range(-1, -8, -1), range(-1, -8, -1)),
                         zip(range(-1, -8, -1), range(1, 8)), zip(range(1, 8), range(-1, -8, -1))]:
            for move in move_seq:
                move = [a + b for a, b in zip(self.pos, move)]
                if move in [i.pos for i in allies] or not in_bounds(move):
                    break
                elif move in [i.pos for i in enemies] + [self.match.enpassant_pos[1]]:
                    moves.append({'pos': move, 'killing': True})
                    break
                else:
                    moves.append({'pos': move, 'killing': False})
                    
        return moves
    
class Queen(BaseFigure):
    name = 'Ферзь'
    fen_symbol = ['q', 'Q']
    def get_moves(self):
        return Bishop.get_moves(self) + Rook.get_moves(self)
    
class King(BaseFigure):
    name = 'Король'
    fen_symbol = ['k', 'K']
    def get_moves(self, for_fen = False):
        allies, enemies = (self.match.whites, self.match.blacks) if self.is_white else (self.match.blacks, self.match.whites)
        moves = []
        for x in [-1, 0, 1]:
            for y in [-1, 0, 1]:
                move = [self.pos[0] + x, self.pos[1] + y]
                if in_bounds(move) and move not in [i.pos for i in allies]:
                    moves.append({'pos': move,
                         'killing': move in [i.pos for i in enemies] + [self.match.enpassant_pos[1]]})
        if not self.moved and not self.in_check():
            Y = 0 if self.is_white else 7
            a_rook = self.match[[0, Y]]
            h_rook = self.match[[7, Y]]
            if all([not self.match[[x, Y]] or for_fen for x in [1, 2, 3]]) and a_rook and not a_rook.moved:
                moves.append({'pos': [2, Y], 'killing': False})
            if all([not self.match[[x, Y]] or for_fen for x in [5, 6]]) and h_rook and not h_rook.moved:
                moves.append({'pos': [6, Y], 'killing': False})
        return moves
        
    def in_checkmate(self):
        allies = self.match.whites if self.is_white else self.match.blacks
        
        checks = []
        for figure in allies:
            actual_pos = figure.pos
            for move in figure.get_moves():
                killed = self.match[move['pos']]
                if killed:
                    del self.match[move['pos']]
                figure.pos = move['pos']
            
                checks.append(self.in_check())
            
                figure.pos = actual_pos
                if killed:
                    self.match[move['pos']] = killed
            
        return all(checks) if checks else False
            
            
    def in_check(self):
        enemies = self.match.blacks if self.is_white else self.match.whites
        enemy_moves = itertools.chain(*[i.get_moves() for i in enemies if type(i) != King])
        
        return self.pos in [i['pos'] for i in enemy_moves]
    
class BaseMatch():
    BOARD_IMG = PIL.Image.open("images/chess/board.png")
    POINTER_IMG = PIL.Image.open("images/chess/pointer.png")
    WRONG_PERSON_MSG = 'Сейчас не ваш ход!'
    
    def __init__(self, fen = STARTPOS):
            self.whites = []
            self.blacks = []
            self.states = []
            self.finished = False
            self.id = ''.join(random.choices(IDSAMPLE, k = 8))
            board, self.is_white_turn, castlings, self.enpassant_pos, self.empty_halfturns, self.turn = [int(i) - 1 if i.isdigit() else i for i in fen.split(' ')]
            
            self.is_white_turn = self.is_white_turn != 'w'
            
            if self.enpassant_pos == '-':
                self.enpassant_pos = [None, None]
            else:
                self.enpassant_pos = decode_pos(self.enpassant_pos)
                self.enpassant_pos = [[self.enpassant_pos[0], int((self.enpassant_pos[1] + 4.5) // 2)], self.enpassant_pos]
                
            board = board.split('/')
            for line in range(8):
                offset = 0
                for column in range(8):
                    if column + offset > 7:
                        break
                    char = board[line][column]
                    if char.isdigit():
                        offset += int(char) - 1
                    else:
                        new = eval(FENSYMBOLS[char.lower()])([column + offset, 7 - line], self, char.isupper())
                        K = 'K' if new.is_white else 'k'
                        Q = 'Q' if new.is_white else 'q'
                        if type(new) == King and K not in castlings and Q not in castlings:
                            new.moved = True
                        elif type(new) == Rook and K not in castlings and Q in castlings and new.pos != [0, 0 if new.is_white else 7]:
                            new.moved = True
                        elif type(new) == Rook and K in castlings and Q not in castlings and new.pos != [7, 0 if new.is_white else 7]:
                            new.moved = True
                        getattr(self, 'whites' if new.is_white else 'blacks').append(new)
                        
    def __getitem__(self, key):
        for figure in self.whites + self.blacks:
            if figure.pos == key:
                return figure
            
    def __setitem__(self, key, value):
        if isinstance(value, list):
            for figure in self.whites + self.blacks:
                if figure.pos == key:
                    figure.pos = value
        elif isinstance(value, BaseFigure):
            if self[key]:
                del self[key]
            (self.whites if value.is_white else self.blacks).append(value)
        else:
            raise TypeError(f'Values can only be subclasses of list or BaseFigure (got {type(value).__name__})')
                
    def __delitem__(self, key):
        for index, figure in enumerate(self.whites if self[key].is_white else self.blacks):
            if figure.pos == key:
                del (self.whites if self[key].is_white else self.blacks)[index]
                
    def get_context(self):
        return {'allies': self.whites if self.is_white_turn else self.blacks,
                'enemies': self.blacks if self.is_white_turn else self.whites,
                'white_turn': self.is_white_turn}
    
    def get_king(self, is_white):
        for figure in (self.whites if is_white else self.blacks):
            if type(figure) == King:
                return figure
    
    def init_turn(self, move = [None, None], promotion = ''):
        context = self.get_context()
        figure = self[move[0]]
        turn_info  = {'figure': figure}
        if figure:
            turn_info.update({'from': encode_pos(move[0]),
                      'to': encode_pos(move[1])})
            killed = self[move[0]].move(move[1])
            turn_info.update({'killed': killed})

            y = 0 if figure.is_white else 7
            if type(figure) == King and move[0][0] - move[1][0] == -2:
                self[[7, y]].move([5, y])
                turn_info['castling'] = 'kingside'
            elif type(figure) == King and move[0][0] - move[1][0] == 2:
                self[[0, y]].move([3, y])
                turn_info['castling'] = 'queenside'
            else:
                turn_info['castling'] = None
                
            if promotion:
                self[move[1]] = eval(FENSYMBOLS[promotion])(move[1], self, figure.is_white)
                self[move[1]].moved = True
                turn_info['promotion'] = promotion
            else:
                turn_info['promotion'] = None
                
        else:
            turn_info.update({'killed': None, 'castling': None, 'promotion': None})
            
        cur_king = self.get_king(not context['white_turn'])
        if cur_king.in_checkmate():
            turn_info['player_gamestate'] = 'checkmate'
            self.finished = True
        elif cur_king.in_check():
            turn_info['player_gamestate'] = 'check'
        elif self.empty_halfturns == 50:
            turn_info['player_gamestate'] = 'stalemate'
            self.finished = True
        else:
            turn_info['player_gamestate'] = 'normal'
            
        self.is_white_turn = not self.is_white_turn
        if self.is_white_turn:
            self.turn += 1
        if turn_info['killed'] or type(turn_info['figure']) == Pawn:
            self.empty_halfturns = 0
        else:
            self.empty_halfturns += 1
        
        self.states.append(self.fen_string())
        
        return turn_info
            
    def visualise_board(self, selected = [None, None], pointers = [], fen = '', special = [], return_bytes = True):
        board = self.BOARD_IMG.copy()
        fen = fen if fen else self.states[-1]
        selected = tuple(selected)
        
        for pos, image in _fentoimagemap(fen).items():
            board.paste('#00cc36' if pos == selected else image,
                        box = _imgpos(pos),
                        mask = image)
        
        for pointer in pointers:
            board.paste('#cc0000' if pointer['killing'] else '#00cc36',
                        box = _imgpos(pointer['pos']),
                        mask = self.POINTER_IMG)
        
        for pointer in special:
            board.paste('#cc0000' if pointer['killing'] else '#3ba7ff',
                        box = _imgpos(pointer['pos']),
                        mask = self.POINTER_IMG)
        
        if return_bytes:
            board = board.convert(mode = 'RGB')
            buffer = io.BytesIO()
            board.save(buffer, format = 'JPEG')
            return buffer.getvalue()
        else:
            return board
        
    def to_gif(self):
        frames = [self.visualise_board(fen = fen, return_bytes = False) for fen in self.states]
            
        buffer = io.BytesIO()
        frames[0].save(buffer, format = 'GIF', save_all = True, append_images = frames[1:], duration = 1000)
        return buffer.getvalue()
        
    def fen_string(self):
        res = [''] * 8

        for line in range(8):
            for column in range(8):
                figure = self[[column, 7 - line]]
                if figure:
                    res[line] += figure.fen_symbol
                else:
                    if res[line] and res[line][-1].isdigit():
                        res[line] = res[line][:-1] + str(int(res[line][-1]) + 1)
                    else:
                        res[line] += '1'
        res = ['/'.join(res)]
        
        res.append('w' if self.is_white_turn else 'b')
        res.append('')
        white_king = self.get_king(True)
        black_king = self.get_king(False)
        if not white_king.moved:
            white_king_moves = [i['pos'] for i in white_king.get_moves(for_fen = True)]
            if [6, 0] in white_king_moves:
                res[-1] += 'K'
            if [2, 0] in white_king_moves:
                res[-1] += 'Q'
        if not black_king.moved:
            black_king_moves = [i['pos'] for i in black_king.get_moves(for_fen = True)]
            if [6, 7] in black_king_moves:
                res[-1] += 'k'
            if [2, 7] in black_king_moves:
                res[-1] += 'q'
        if white_king.moved and black_king.moved:
            res[-1] += '-'
        
        res.append(encode_pos(self.enpassant_pos[1]) if self.enpassant_pos[0] else '-')
        
        res.append(str(self.empty_halfturns))
        
        res.append(str(self.turn))
        
        return ' '.join(res)
        
class GroupMatch(BaseMatch):
    def __init__(self, player1, player2, match_chat, **kwargs):
        self.player1 = player1
        self.player2 = player2
        self.chat_id = match_chat
        self.ids = {}
        self.last_msg = {}
        super().__init__(**kwargs)
        
    def get_context(self):
        context = super().get_context()
        context.update({'player': self.player1 if context['white_turn'] else self.player2,
                        'opponent': self.player2 if context['white_turn'] else self.player1})
        return context

    def init_turn(self, move = [None, None], turn_info = None, promotion = ''):
        res = turn_info if turn_info else super().init_turn(move = move, promotion = promotion)
        context = self.get_context()
        if res['player_gamestate'] == 'checkmate':
            msg = f"Игра окончена: шах и мат!\nХодов: {self.turn - 1}.\nПобедитель: {context['opponent'].name}."
        elif res['player_gamestate'] == 'stalemate':
            msg = f"Игра окончена: за последние 50 ходов не было убито ни одной фигуры и не сдвинуто ни одной пешки - ничья!\nХодов: {self.turn - 1}"
        else:
            msg = f"Ход {self.turn}"
            if res['figure']:
                msg += f"\n{res['figure'].name}{' -> '+eval(FENSYMBOLS[res['promotion']]).name if res['promotion'] else ''}: {res['from']} -> {res['to']}"
                if res['castling']:
                    msg += f' ({"Короткая" if res["castling"] == "kingside" else "Длинная"} рокировка)'
            else:
                msg += '\n'
            
            if res['killed']:
                msg += f"\n{res['killed']} игрока {context['player'].name} убит{'а' if res['killed'].name in ['Пешка', 'Ладья'] else ''}!"
            else:
                msg += '\n'
                
            if res['player_gamestate'] == 'check':
                msg += f'\nИгроку {context["player"].name} поставлен шах!'
            else:
                msg += '\n'
                
            msg += f"\nХодит { context['player'].name }; выберите действие:"
            
        self.init_msg = {
                 'msg_id': self.ids.get(self.chat_id),
                 'chat_id': self.chat_id,
                 'img': self.visualise_board() if not self.finished else None,
                 'gif': self.to_gif() if self.finished else None,
                 'text': msg,
                 'expected_uid': context['player'].id, 
                 'answers': [
                     [{'text': 'Ходить', 'callback_data': ['TURN']}],
                     [{'text': 'Сдаться', 'callback_data': ['SURRENDER']}]
                 ] if not self.finished else []
                }
        self.last_msg = self.init_msg
        return [self.last_msg]
    
    def handle_input(self, args):
        context = self.get_context()
        if args[0] == 'INIT_MSG':
            return [{
                **self.init_msg,
                'msg_id': self.ids[self.chat_id]
            }]
            
        if args[0] == 'TURN':
            figure_buttons = [[{'text': 'Назад', 'callback_data': ['INIT_MSG']}]]
            for figure in context['allies']:
                if next(filter(figure.is_legal, [i['pos'] for i in figure.get_moves()]), None):
                    figure_buttons.append([{'text': str(figure), 'callback_data': ['CHOOSE_FIGURE', figure.pos]}])
            new_text = self.last_msg['text'].split('\n')
            new_text[-1] = f"Ходит {context['player'].name}; выберите фигуру:"
            
            self.last_msg = {
                **self.init_msg,
                'msg_id': self.ids[self.chat_id],
                'text': '\n'.join(new_text),
                'answers': figure_buttons
            }
            
            return [self.last_msg]
        
        elif args[0] == 'SURRENDER':
            self.finished = True
            return [{
                **self.init_msg,
                'msg_id': self.ids[self.chat_id],
                'img': None,
                'gif': self.to_gif(),
                'text': f"Игра окончена: {context['player'].name} сдался.\nХодов: {self.turn - 1}.\nПобедитель: {context['opponent'].name}.",
                'answers': []
            }]
            
        elif args[0] == 'CHOOSE_FIGURE':
            dest_buttons = [[{'text': 'Назад', 'callback_data': ['TURN']}]]
            figure = self[args[1]]
            moves = list(filter(lambda move: figure.is_legal(move['pos']), figure.get_moves()))
            for move in moves:
                if type(figure) == Pawn and move['pos'][1] == (7 if figure.is_white else 0):
                    dest_buttons.append([{'text': ('❌⏫' if move['killing'] else '⏫')+encode_pos(move['pos']),
                                          'callback_data': ['PROMOTION_MENU', args[1], move['pos']]}])
                else:
                    dest_buttons.append([{'text': ('❌' if move['killing'] else '')+encode_pos(move['pos']),
                                          'callback_data': ['MOVE', args[1], move['pos']]}])
            new_text = self.last_msg['text'].split('\n')
            new_text[-1] = f"Ходит {context['player'].name}; выберите новое место фигуры:"
            
            self.last_msg = {
                **self.last_msg,
                'img': self.visualise_board(selected = args[1], pointers = moves),
                'text': '\n'.join(new_text),
                'answers': dest_buttons
            }
            
            return [self.last_msg]
            
        elif args[0] == 'PROMOTION_MENU':
            figures = [
                [{'text': 'Ферзь', 'callback_data': ['PROMOTION', args[1], args[2], 'q']}],
                [{'text': 'Конь', 'callback_data': ['PROMOTION', args[1], args[2], 'n']}],
                [{'text': 'Слон', 'callback_data': ['PROMOTION', args[1], args[2], 'b']}],
                [{'text': 'Ладья', 'callback_data': ['PROMOTION', args[1], args[2], 'r']}]
            ]
            new_text = self.last_msg['text'].split('\n')
            new_text[-1] = f"Ходит {context['player'].name}; выберите фигуру, в которую првератится пешка:"
            
            self.last_msg = {
                **self.last_msg,
                'img': self.visualise_board(selected = args[1], special = [{'pos': args[2], 'killing': False}]),
                'text': '\n'.join(new_text),
                'answers': figures
            }
            
            return [self.last_msg]
            
        elif args[0] == 'PROMOTION':
            return self.init_turn(move = args[1:3], promotion = args[3])
            
        elif args[0] == 'MOVE':
            return self.init_turn(move = args[1:3])
        
class PMMatch(BaseMatch):
    def __init__(self, player1, player2, chat1, chat2, **kwargs):
        self.player1 = player1
        self.player2 = player2
        self.chat_id1 = chat1
        self.chat_id2 = chat2
        self.ids = {}
        self.last_msg = {}
        super().__init__(**kwargs)
        
    def get_context(self):
        context = super().get_context()
        context.update({'player': self.player1 if context['white_turn'] else self.player2,
                'opponent': self.player2 if context['white_turn'] else self.player1,
                'player_chat': self.chat_id1 if context['white_turn'] else self.chat_id2,
                'opponent_chat': self.chat_id2 if context['white_turn'] else self.chat_id1})
        
        return context
        
    def init_turn(self, move = [None, None], turn_info = None, promotion = ''):
        res = turn_info if turn_info else super().init_turn(move = move, promotion = promotion)
        context = self.get_context()
        if res['player_gamestate'] == 'checkmate':
            player_msg = opponent_msg = f"Игра окончена: шах и мат!\nХодов: {self.turn - 1}.\nПобедитель: {context['opponent'].name}."
        elif res['player_gamestate'] == 'stalemate':
            player_msg = opponent_msg = f"Игра окончена: за последние 50 ходов не было убито ни одной фигуры и не сдвинуто ни одной пешки - ничья!\nХодов: {self.turn - 1}"
        else:
            player_msg = f"Ход {self.turn}"
            if res['figure']:
                player_msg += f"\n{res['figure'].name}{' -> '+eval(FENSYMBOLS[res['promotion']]).name if res['promotion'] else ''}: {res['from']} -> {res['to']}"
                if res['castling']:
                    player_msg += f' ({"Короткая" if res["castling"] == "kingside" else "Длинная"} рокировка)'
            else:
                player_msg += '\n'
            
            if res['killed']:
                player_msg += f"\n{res['killed']} игрока {context['player'].name} убит{'а' if res['killed'].name in ['Пешка', 'Ладья'] else ''}!"
            else:
                player_msg += '\n'
                
            if res['player_gamestate'] == 'check':
                player_msg += f'\nИгроку {context["player"].name} поставлен шах!'
            else:
                player_msg += '\n'
                
            opponent_msg = player_msg
                
            player_msg += '\nВыберите действие:'
            opponent_msg += f"\nХодит {context['player'].name}"
            
        img = self.visualise_board() if not self.finished else None
        gif  = self.to_gif() if self.finished else None
        self.init_msg = {
            'player': {
                'msg_id': self.ids.get(context['player_chat']),
                'chat_id': context['player_chat'],
                'img': img,
                'gif': gif,
                'text': player_msg,
                'expected_uid': context['player'].id,
                'answers': [
                    [{'text': 'Ходить', 'callback_data': ['TURN']}],
                    [{'text': 'Сдаться', 'callback_data': ['SURRENDER']}]
                ] if res['player_gamestate'] != 'checkmate' else []
            },'opponent': {
                'msg_id': self.ids.get(context['opponent_chat']),
                'chat_id': context['opponent_chat'],
                'img': img,
                'gif': gif,
                'text': opponent_msg
            }
        }
        self.last_msg = self.init_msg
        return list(self.last_msg.values())
    
    def handle_input(self, args):
        context = self.get_context()
        if args[0] == 'INIT_MSG':
            return [{
                **self.init_msg['player'],
                'msg_id': self.ids[context['player_chat']]
            }]
        
        if args[0] == 'TURN':
            figure_buttons = [[{'text': 'Назад', 'callback_data': ['INIT_MSG']}]]
            for figure in context['allies']:
                if next(filter(figure.is_legal, [i['pos'] for i in figure.get_moves()]), None):
                    figure_buttons.append([{'text': str(figure), 'callback_data': ['CHOOSE_FIGURE', figure.pos]}])
            new_text = self.last_msg['player']['text'].split('\n')
            new_text[-1] = f"Выберите фигуру:"
            
            self.last_msg['player'] = {
                **self.init_msg['player'],
                'img': self.visualise_board(),
                'msg_id': self.ids[context['player_chat']],
                'text': '\n'.join(new_text),
                'answers': figure_buttons
            }
            
            return [self.last_msg['player']]
        
        elif args[0] == 'SURRENDER':
            self.finished = True
            gif = self.to_gif()
            return [{
                **self.last_msg['player'],
                'msg_id': self.ids[context['player_chat']],
                'img': None,
                'gif': gif,
                'text': f"Игра окончена: {context['player'].name} сдался.\nХодов: {self.turn - 1}.\nПобедитель: {context['opponent'].name}.",
                'answers': []
            }, {
                **self.last_msg['opponent'],
                'msg_id': self.ids.get(context['opponent_chat']),
                'img': None,
                'gif': gif,
                'text': f"Игра окончена: {context['player'].name} сдался.\nХодов: {self.turn - 1}.\nПобедитель: {context['opponent'].name}.",
                'answers': []
            }]
            
        
        elif args[0] == 'CHOOSE_FIGURE':
            dest_buttons = [[{'text': 'Назад', 'callback_data': ['TURN']}]]
            figure = self[args[1]]
            moves = list(filter(lambda move: figure.is_legal(move['pos']), figure.get_moves()))
            for move in moves:
                if type(figure) == Pawn and move['pos'][1] == (7 if figure.is_white else 0):
                    dest_buttons.append([{'text': ('❌⏫' if move['killing'] else '⏫')+encode_pos(move['pos']),
                                          'callback_data': ['PROMOTION_MENU', args[1], move['pos']]}])
                else:
                    dest_buttons.append([{'text': ('❌' if move['killing'] else '')+encode_pos(move['pos']),
                                          'callback_data': ['MOVE', args[1], move['pos']]}])
            new_text = self.last_msg['player']['text'].split('\n')
            new_text[-1] = f"Выберите новое место фигуры:"
            
            self.last_msg['player'] = {
                **self.last_msg['player'],
                'img': self.visualise_board(selected = args[1], pointers = moves),
                'text': '\n'.join(new_text),
                'answers': dest_buttons
            }
            
            return [self.last_msg['player']]
            
        elif args[0] == 'PROMOTION_MENU':
            figures = [
                [{'text': 'Ферзь', 'callback_data': ['PROMOTION', args[1], args[2], 'q']}],
                [{'text': 'Конь', 'callback_data': ['PROMOTION', args[1], args[2], 'n']}],
                [{'text': 'Слон', 'callback_data': ['PROMOTION', args[1], args[2], 'b']}],
                [{'text': 'Ладья', 'callback_data': ['PROMOTION', args[1], args[2], 'r']}]
            ]
            new_text = self.last_msg['player']['text'].split('\n')
            new_text[-1] = f"Выберите фигуру, в которую првератится пешка:"
            
            self.last_msg['player'] = {
                **self.last_msg,
                'img': self.visualise_board(selected = args[1], special = [{'pos': args[2], 'killing': False}]),
                'text': '\n'.join(new_text),
                'answers': figures
            }
            
            return [self.last_msg['player']]
            
        elif args[0] == 'PROMOTION':
            return self.init_turn(move = args[1:3], promotion = args[3])
        
        elif args[0] == 'MOVE':
            return self.init_turn(move = args[1:3])
        
class AIMatch(PMMatch):
    def __init__(self, player, chat, player2 = None, **kwargs):
        ai_player = player2 if player2 else chat.bot.get_me()
        super().__init__(player, ai_player, chat.id, 0, **kwargs)
        self.engine_api = subprocess.Popen(os.environ['ENGINE_FILENAME'], bufsize = 1, universal_newlines = True, shell = True, 
                stdin = subprocess.PIPE, stdout = subprocess.PIPE)
        
        self.engine_api.stdout.readline()
        
        
    def init_turn(self, setup = False, **kwargs):
        context = self.get_context()
        if setup:
            return [{
                'chat_id': self.chat_id1,
                'text': 'Выберите уровень сложности:',
                'img': self.visualise_board(fen = STARTPOS),
                'expected_uid': self.player1.id,
                'answers': [
                    [{'text': 'Низкий', 'callback_data': ['SKILL_LEVEL', '1350']}],
                    [{'text': 'Средний', 'callback_data': ['SKILL_LEVEL', '1850']}],
                    [{'text': 'Высокий', 'callback_data': ['SKILL_LEVEL', '2350']}],
                    [{'text': 'Легендарный', 'callback_data': ['SKILL_LEVEL', '2850']}]
                ]
            }]
        
        else:
            turn_info = BaseMatch.init_turn(self, **kwargs)
            if turn_info['player_gamestate'] == 'checkmate':
                return super().init_turn(turn_info = turn_info)
            
            self.engine_api.stdin.write(f'position fen {self.states[-1]}\n')
            self.engine_api.stdin.write(f'go depth 2\n')
            for line in self.engine_api.stdout:
                if 'bestmove' in line:
                    turn = line.split(' ')[1].strip('\n')
                    break
            return super().init_turn(move = [decode_pos(turn[:2]), decode_pos(turn[2:4])],
                                     promotion = turn[-1] if len(turn) == 5 else '')

    def handle_input(self, args):
        if args[0] == 'SKILL_LEVEL':
            self.engine_api.stdin.write(f'setoption name UCI_Elo value {args[1]}\n')
            return super().init_turn()
        else:
            return super().handle_input(args)
