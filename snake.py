import os
import time
import random
from typing import Dict, List, Type, Any
from dataclasses import dataclass
from enum import Enum, auto
from rx.subject import Subject

# ECS Core
@dataclass
class Entity:
    id: int
    components: Dict[Type, Any]

class World:
    def __init__(self):
        self.entities: Dict[int, Entity] = {}
        self.next_entity_id: int = 0
        self.components: Dict[Type, Dict[int, Any]] = {}
        self.systems: List['System'] = []

    def create_entity(self) -> int:
        entity_id = self.next_entity_id
        self.next_entity_id += 1
        self.entities[entity_id] = Entity(entity_id, {})
        return entity_id

    def add_component(self, entity_id: int, component: Any):
        component_type = type(component)
        self.entities[entity_id].components[component_type] = component
        if component_type not in self.components:
            self.components[component_type] = {}
        self.components[component_type][entity_id] = component

    def get_component(self, entity_id: int, component_type: Type) -> Any:
        return self.entities[entity_id].components.get(component_type)

    def get_entities_with_component(self, component_type: Type) -> List[int]:
        return list(self.components.get(component_type, {}).keys())

    def add_system(self, system: 'System'):
        self.systems.append(system)

    def update(self, dt: float):
        for system in self.systems:
            system.update(self, dt)

class System:
    def update(self, world: World, dt: float):
        pass

# Game Components
class Direction(Enum):
    UP = auto()
    DOWN = auto()
    LEFT = auto()
    RIGHT = auto()

@dataclass
class Position:
    x: int
    y: int

@dataclass
class Velocity:
    direction: Direction

@dataclass
class Snake:
    body: List[tuple[int, int]]
    growth_pending: int = 0

@dataclass
class Food:
    position: Position

@dataclass
class Score:
    value: int = 0
    score_changed: Subject = Subject()

@dataclass
class Grid:
    width: int
    height: int

@dataclass
class GameState:
    is_game_over: bool = False
    game_over_subject: Subject = Subject()

# Game Systems
class MovementSystem(System):
    def update(self, world: World, dt: float):
        for entity_id in world.get_entities_with_component(Snake):
            snake = world.get_component(entity_id, Snake)
            velocity = world.get_component(entity_id, Velocity)
            grid = world.get_component(entity_id, Grid)

            # Move the snake
            head = snake.body[0]
            new_head = None
            if velocity.direction == Direction.UP:
                new_head = (head[0], (head[1] - 1) % grid.height)
            elif velocity.direction == Direction.DOWN:
                new_head = (head[0], (head[1] + 1) % grid.height)
            elif velocity.direction == Direction.LEFT:
                new_head = ((head[0] - 1) % grid.width, head[1])
            elif velocity.direction == Direction.RIGHT:
                new_head = ((head[0] + 1) % grid.width, head[1])

            snake.body.insert(0, new_head)
            if snake.growth_pending > 0:
                snake.growth_pending -= 1
            else:
                snake.body.pop()

class CollisionSystem(System):
    def update(self, world: World, dt: float):
        for entity_id in world.get_entities_with_component(Snake):
            snake = world.get_component(entity_id, Snake)
            food = world.get_component(entity_id, Food)
            score = world.get_component(entity_id, Score)
            game_state = world.get_component(entity_id, GameState)

            # Check for collision with food
            if snake.body[0] == (food.position.x, food.position.y):
                snake.growth_pending += 1
                score.value += 1
                score.score_changed.on_next(score.value)
                self._respawn_food(world, entity_id)

            # Check for collision with self
            if snake.body[0] in snake.body[1:]:
                game_state.is_game_over = True
                game_state.game_over_subject.on_next(True)

    def _respawn_food(self, world: World, entity_id: int):
        snake = world.get_component(entity_id, Snake)
        food = world.get_component(entity_id, Food)
        grid = world.get_component(entity_id, Grid)

        while True:
            new_x = random.randint(0, grid.width - 1)
            new_y = random.randint(0, grid.height - 1)
            if (new_x, new_y) not in snake.body:
                food.position = Position(new_x, new_y)
                break

class InputSystem(System):
    def __init__(self):
        self.pending_direction = None

    def set_direction(self, direction: Direction):
        self.pending_direction = direction

    def update(self, world: World, dt: float):
        if self.pending_direction is not None:
            for entity_id in world.get_entities_with_component(Velocity):
                velocity = world.get_component(entity_id, Velocity)
                # Prevent 180-degree turns
                if (self.pending_direction == Direction.UP and velocity.direction != Direction.DOWN) or \
                   (self.pending_direction == Direction.DOWN and velocity.direction != Direction.UP) or \
                   (self.pending_direction == Direction.LEFT and velocity.direction != Direction.RIGHT) or \
                   (self.pending_direction == Direction.RIGHT and velocity.direction != Direction.LEFT):
                    velocity.direction = self.pending_direction
            self.pending_direction = None

# Main Game Loop
class SnakeGame:
    def __init__(self, width: int, height: int):
        self.world = World()
        self.input_system = InputSystem()

        # Create systems
        self.world.add_system(self.input_system)
        self.world.add_system(MovementSystem())
        self.world.add_system(CollisionSystem())

        # Create game entity
        game_entity = self.world.create_entity()
        self.world.add_component(game_entity, Grid(width, height))
        self.world.add_component(game_entity, Snake([(width // 2, height // 2)]))
        self.world.add_component(game_entity, Velocity(Direction.RIGHT))
        self.world.add_component(game_entity, Food(Position(0, 0)))
        self.world.add_component(game_entity, Score())
        self.world.add_component(game_entity, GameState())

        # Spawn initial food
        collision_system = next(s for s in self.world.systems if isinstance(s, CollisionSystem))
        collision_system._respawn_food(self.world, game_entity)

    def update(self):
        self.world.update(0.1)  # Fixed time step
        game_state = self.world.get_component(0, GameState)
        return game_state.is_game_over

    def set_direction(self, direction: Direction):
        self.input_system.set_direction(direction)

# Game UI
class SnakeGameUI:
    def __init__(self, width: int, height: int):
        self.game = SnakeGame(width, height)
        self.width = width
        self.height = height

    def start(self):
        # Set up reactive subscribers
        score = self.game.world.get_component(0, Score)
        score.score_changed.subscribe(lambda s: print(f"Score: {s}"))

        game_state = self.game.world.get_component(0, GameState)
        game_state.game_over_subject.subscribe(lambda _: print("Game Over!"))

        # Start the game loop
        while True:
            self.render()
            key = input("Enter direction (w/a/s/d) or q to quit: ").lower()
            if key == 'q':
                break
            elif key in ['w', 'a', 's', 'd']:
                direction = {'w': Direction.UP, 'a': Direction.LEFT, 's': Direction.DOWN, 'd': Direction.RIGHT}[key]
                self.game.set_direction(direction)

            is_game_over = self.game.update()
            if is_game_over:
                self.render()
                print("Game Over!")
                break

    def render(self):
        os.system('cls' if os.name == 'nt' else 'clear')
        
        grid = [['.' for _ in range(self.width)] for _ in range(self.height)]
        
        snake = self.game.world.get_component(0, Snake)
        food = self.game.world.get_component(0, Food)
        score = self.game.world.get_component(0, Score)
        
        for segment in snake.body:
            grid[segment[1]][segment[0]] = 'O'
        grid[snake.body[0][1]][snake.body[0][0]] = '@'
        
        grid[food.position.y][food.position.x] = 'F'
        
        print(f"Score: {score.value}")
        for row in grid:
            print(''.join(row))

if __name__ == "__main__":
    game_ui = SnakeGameUI(20, 15)
    game_ui.start()
