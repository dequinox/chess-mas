import time
import asyncio
from spade.agent import Agent
from spade.message import Message
from spade.behaviour import FSMBehaviour, State
from spade.behaviour import OneShotBehaviour, CyclicBehaviour

import chess
import chess.svg
import chess.pgn
import chess.engine

engine = chess.engine.SimpleEngine.popen_uci("/usr/bin/stockfish")
board = chess.Board()
limit = chess.engine.Limit(depth=1)

Commanders = {
    "black": "betelgeuse@jabber.ccc.de",
    "white": "aldebaran@jabber.ccc.de"
}

PiecesJid = {
    'white': [
            "WhiteR1@jabber.no",
            "WhiteK1@jabber.sk",
            "WhiteB1@jabber.sk",
            "WhiteQ@jabbim.com",
            "WhiteKing@jabber.ccc.de",
            "WhiteB2@creep.im",
            "WhiteK2@deshalbfrei.org",
            "WhiteR2@jabber.ccc.de",
            "WhiteP1@404.city",
            "WhiteP2@blabber.im",
            "WhiteP3@blabber.im",
            "WhiteP4@creep.im",
            "WhiteP5@deshalbfrei.org",
            "WhiteP6@im.apinc.org",
            "WhiteP7@jabber.ccc.de",
            "WhiteP8@jabber.cz",
    ],
    'black': [
            "BlackP1@404.city",
            "BlackP2@jabber.no",
            "BlackP3@jabber.sk",
            "WhiteP4@jabber.sk",
            "BlackP5@blabber.im",
            "BlackP6@creep.im",
            "BlackP7@deshalbfrei.org",
            "BlackP8@jabber.ccc.de",
            "BlackR1@blabber.im",
            "BlackK1@im.apinc.org",
            "BlackB1@jabber.no",
            "BlackQ@jabber.sk",
            "BlackKing@404.city",
            "BlackB2@blabber.im",
            "BlackK2@creep.im",
            "BlackR2@deshalbfrei.org",
    ]
}

Pieces = {}

def get_opposite_color(color):
    if color == "white":
        return "black"
    else:
        return "white"

def get_possible_moves(position):
    possible_moves = [None]
    for square in chess.SQUARES:
        move = chess.Move(position, square)
        if move in board.legal_moves:
            if not possible_moves[0] is None:
                possible_moves.append(move)
            else:
                possible_moves[0] = move
    return possible_moves


class Piece(Agent):
    class PostBehaviour(CyclicBehaviour):
        async def on_start(self):
            self.state = "ALIVE"
            
        async def run(self):
            msg = await self.receive()
            if msg:
                type = msg.body.split()[0]
                if type == "REQUEST":
                    if self.state == "ALIVE":
                        possible_moves = get_possible_moves(int(self.get("position")))
                        if not possible_moves[0] is None:
                            move = engine.play(board, limit=limit, info=chess.engine.INFO_ALL, root_moves=possible_moves)
                            score = move.info['score'].relative.score() / 100
        
                            #print("Request accepted: Sending a move " + move.move.uci())
                            message = Message(to=Commanders[self.get("color")])
                            message.body = "MOVE " + move.move.uci() + " " + str(score)  # Set the message content
                            await self.send(message)
                        else:
                            #print("Request accepted: No moves found " + self.get("position"))
                            message = Message(to=Commanders[self.get("color")])
                            message.body = "NO_MOVE"  # Set the message content
                            await self.send(message)
                    else:
                        #print("Request accepted: DEAD")
                        message = Message(to=Commanders[self.get("color")])
                        message.body = "NO_MOVE"  # Set the message content
                        await self.send(message)
                if type == "MOVE":
                    to = msg.body.split()[1]
                    #print("Moving to new position: " + to)
                    self.set("position", to)
                if type == "KILL":
                    to = msg.body.split()[1]
                    if self.get("position") == to:
                        self.state = "DEAD"
                        #print("______________________________________________________________KILED")
            await asyncio.sleep(1)

    async def setup(self):
        print("Pawn starting . . .")
        b = self.PostBehaviour()
        self.add_behaviour(b)


class Commander(Agent):
    class CommanderBehaviour(CyclicBehaviour):
        async def on_start(self):
            self.moves_counter = 0
            self.best_move_jid = "none"
            self.best_move = "none"
            self.highest_score = -1000.0
            self.state = "WAITING"

        async def run(self):
            msg = await self.receive()
            if self.moves_counter >= 16:
                self.state = "MAKE_MOVE"
            if self.state == "MAKE_MOVE":

                move = chess.Move.from_uci(self.best_move)
                for jid in PiecesJid[get_opposite_color(self.get("color"))]:
                    message = Message(to=jid)
                    message.body = "KILL " + str(move.to_square)
                    await self.send(message)

                message = Message(to=str(self.best_move_jid))
                message.body = "MOVE " + str(move.to_square)
                await self.send(message)

                #print("Evaluated Best move: " + self.best_move + " " + self.get("color"))
                board.push(chess.Move.from_uci(self.best_move))
                print(board)

                message = Message(to=Commanders[get_opposite_color(self.get("color"))])
                message.body = "PASSING_TURN"
                await self.send(message)
                #print("SENT TO: " + Commanders[get_opposite_color(self.get("color"))])
                self.state = "WAITING"
                self.highest_score = -1000.0
                self.best_move = "none"
                self.moves_counter = 0
                self.best_move_jid = "none"
            if msg:
                type = msg.body.split()[0]
                if type == "PASSING_TURN" and self.state == "WAITING":
                    #print("Turn Accepted: " + self.get("color"))
                    for jid in PiecesJid[self.get("color")]:
                        message = Message(to=jid)
                        message.body = "REQUEST"
                        await self.send(message)
                    self.state = "EVALUATION"
                    self.highest_score = -1000.0
                    self.best_move = "none"
                    self.moves_counter = 0
                    self.best_move_jid = "none"
                if type == "MOVE" and self.state == "EVALUATION":
                    body = msg.body.split()
                    move, score = body[1], body[2]
                    #print("Move Accepted: " + move + " " + score)
                    if float(score) > self.highest_score:
                        self.highest_score = float(score)
                        self.best_move = move
                        self.best_move_jid = msg.sender
                    self.moves_counter = self.moves_counter + 1
                if type == "NO_MOVE":
                    self.moves_counter = self.moves_counter + 1
            await asyncio.sleep(1)

    async def setup(self):
        print("Commander starting at position")
        b = self.CommanderBehaviour()
        self.add_behaviour(b)


class Judge(Agent):
    class ObservingBehaviour(CyclicBehaviour):
        async def on_start(self):
            msg = Message(to="aldebaran@jabber.ccc.de")
            msg.body = "PASSING_TURN"
            await self.send(msg)

        async def run(self):
            print("Runing")
            await asyncio.sleep(10)

        async def on_end(self):
            print("Behaviour finished with exit code {}.".format(self.exit_code))

    async def setup(self):
        print("Judge starting . . .")
        b = self.ObservingBehaviour()
        self.add_behaviour(b)


if __name__ == "__main__":

    judge = Judge("ChessJudge@404.city", "innopolis")

    blackCommander = Commander("betelgeuse@jabber.ccc.de", "innopolis")
    blackCommander.set("color", "black")
    
    whiteCommander = Commander("aldebaran@jabber.ccc.de", "innopolis")
    whiteCommander.set("color", "white")
    
    Pieces = {
        'white': [
            Piece("WhiteR1@jabber.no", "innopolis"),
            Piece("WhiteK1@jabber.sk", "innopolis"),
            Piece("WhiteB1@jabber.sk", "innopolis"),
            Piece("WhiteQ@jabbim.com", "innopolis"),
            Piece("WhiteKing@jabber.ccc.de", "innopolis"),
            Piece("WhiteB2@creep.im", "innopolis"),
            Piece("WhiteK2@deshalbfrei.org", "innopolis"),
            Piece("WhiteR2@jabber.ccc.de", "innopolis"),
            Piece("WhiteP1@404.city", "innopolis"),
            Piece("WhiteP2@blabber.im", "innopolis"),
            Piece("WhiteP3@blabber.im", "innopolis"),
            Piece("WhiteP4@creep.im", "innopolis"),
            Piece("WhiteP5@deshalbfrei.org", "innopolis"),
            Piece("WhiteP6@im.apinc.org", "innopolis"),
            Piece("WhiteP7@jabber.ccc.de", "innopolis"),
            Piece("WhiteP8@jabber.cz", "innopolis"),
        ],
        'black': [
            Piece("BlackP1@404.city", "innopolis"),
            Piece("BlackP2@jabber.no", "innopolis"),
            Piece("BlackP3@jabber.sk", "innopolis"),
            Piece("WhiteP4@jabber.sk", "innopolis"),
            Piece("BlackP5@blabber.im", "innopolis"),
            Piece("BlackP6@creep.im", "innopolis"),
            Piece("BlackP7@deshalbfrei.org", "innopolis"),
            Piece("BlackP8@jabber.ccc.de", "innopolis"),
            Piece("BlackR1@blabber.im", "innopolis"),
            Piece("BlackK1@im.apinc.org", "innopolis"),
            Piece("BlackB1@jabber.no", "innopolis"),
            Piece("BlackQ@jabber.sk", "innopolis"),
            Piece("BlackKing@404.city", "innopolis"),
            Piece("BlackB2@blabber.im", "innopolis"),
            Piece("BlackK2@creep.im", "innopolis"),
            Piece("BlackR2@deshalbfrei.org", "innopolis"),
        ]
    }


    for i in range(16):
        Pieces['white'][i].set("color", "white")
        Pieces['white'][i].set("position", str(i))
        Pieces['white'][i].start().result()

    for i in range(16):
        Pieces['black'][i].set("color", "black")
        Pieces['black'][i].set("position", str(48 + i))
        Pieces['black'][i].start().result()

    blackCommander.start().result()
    whiteCommander.start().result()

    judge.start()

    print("Wait until user interrupts with ctrl+C")
    while judge.is_alive():
        try:
            time.sleep(1)
        except KeyboardInterrupt:
            break