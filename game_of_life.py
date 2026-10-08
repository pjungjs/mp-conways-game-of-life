import random

'''
Conway's Game of Life
A zero-player cellular automaton simulation devised by British mathematician John Horton Conway in 1970.

Rules (B3/S23):
1. Any live cell with fewer than two live neighbours dies (underpopulation).
2. Any live cell with two or three live neighbours lives on to the next generation.
3. Any live cell with more than three live neighbours dies (overpopulation).
4. Any dead cell with exactly three live neighbours becomes a live cell (reproduction).

In another words:
- Birth (B3): A dead cell turns alive if it has exactly 3 living neighbors.
- Survival (S23): A living cell stays alive if it has 2 or 3 living neighbors. Otherwise, it dies of underpopulation (<2) or overcrowding (>3).

---

setup:
- user can input the grid size and the initial state of the grid, where 0 represents a dead cell and 1 represents a live cell.
- dead cell and not alive cell are the same, so are the new born cell and the alive cell.
- to reflect the current state of the grid only to the next generation and not the current one, we mark the cells that
  are about to change (WILL_BE_ALIVE / WILL_BE_DEAD) and settle them in a second pass, so no second grid is needed.

check neighbors:
- to check a cell's 8 neightbors, we need to check current index -1 to current index +1 for both rows and columns.
- to count the number of alive neighbors, we don't need to know the exact position of each neighbor, we just need to know how many of them are alive.
- we can use a 3x3 slice of the grid centered on the cell, minus the cell itself, to get the number of total live neighbors.

progression:
- it should display the number of the current generation and its number of alive cells in the grid.
- it should allow the user to resume/pause/quit the simultation, control its iteration speed and set max iterations.
- it should allow the user to reset the grid to its initial state or randomize it by clicking in the grid.

---

This file is the single source of truth for the game. The web page (index.html + js/main.js) runs it in the
browser through Pyodide and only draws the grid and forwards what the user does (clicks, buttons, inputs).
'''

# cell states
DEAD_CELL = 0
LIVE_CELL = 1
WILL_BE_ALIVE = 2   # dead now, becomes alive next generation (only exists while a step is running)
WILL_BE_DEAD = 3    # alive now, dies next generation (only exists while a step is running)

# whether a cell counts as alive for the current generation, indexed by state
# (a cell marked WILL_BE_DEAD was still alive when the others looked at it)
ALIVE_BY_STATE = (0, 1, 0, 1)

MAX_NEIGHBORS = 8  # a cell touches at most 8 others, so rules only use the digits 0-8

DEFAULT_SIZE = 100
MIN_SIZE = 3
MAX_SIZE = 300
DEFAULT_BIRTH = (3,)
DEFAULT_SURVIVAL = (2, 3)
MIN_GENERATIONS = 1
MAX_GENERATIONS = 1000
DEFAULT_MAX_GENERATIONS = 250
RANDOM_FILL = 0.2  # chance that a cell starts alive when randomizing (so about 20% of the grid)

# why a game can stop on its own (see Game.stop_reason)
REASON_MAX = "max"
REASON_EXTINCT = "extinct"
REASON_STABLE = "stable"


def is_alive(cell: int) -> bool:
  """Alive for the current generation: live, or about to die (it was still alive when the others looked)."""
  return bool(ALIVE_BY_STATE[cell])


def count_alive_neighbors(grid: list[list[int]], row: int, col: int) -> int:
  """Counts the live cells in the 3x3 block around (row, col), minus the cell itself. Cells off the grid count as dead."""
  first_col = max(col - 1, 0)  # a slice stops at the end of a row by itself, but a negative start would wrap around
  alive_neighbors = 0

  for neighbor_row in range(max(row - 1, 0), min(row + 2, len(grid))):
    for cell in grid[neighbor_row][first_col:col + 2]:
      alive_neighbors += ALIVE_BY_STATE[cell]

  return alive_neighbors - ALIVE_BY_STATE[grid[row][col]]


def process_next_generation(
  grid: list[list[int]],
  birth: tuple[int, ...] = DEFAULT_BIRTH,
  survival: tuple[int, ...] = DEFAULT_SURVIVAL,
) -> int:
  """
  Advances the grid one generation in place (no second grid).

  A dead cell is born when its neighbor count is in `birth`.
  A live cell survives when its neighbor count is in `survival`; otherwise it dies.

  Returns how many cells changed, so the caller can tell when the grid has stopped evolving.
  """
  n_rows, n_cols = len(grid), len(grid[0])

  # pass 1: mark every cell that is going to change, without changing its current alive-ness
  for row in range(n_rows):
    for col in range(n_cols):
      current_cell = grid[row][col]
      alive_neighbors = count_alive_neighbors(grid, row, col)

      if current_cell == LIVE_CELL and alive_neighbors not in survival:
        grid[row][col] = WILL_BE_DEAD  # cell dies
      elif current_cell == DEAD_CELL and alive_neighbors in birth:
        grid[row][col] = WILL_BE_ALIVE  # cell becomes alive

  # pass 2: settle the marks into the next generation
  changed_cells = 0
  for row in range(n_rows):
    for col in range(n_cols):
      if grid[row][col] == WILL_BE_DEAD:
        grid[row][col] = DEAD_CELL
        changed_cells += 1
      elif grid[row][col] == WILL_BE_ALIVE:
        grid[row][col] = LIVE_CELL
        changed_cells += 1

  return changed_cells


def format_rule(birth: tuple[int, ...], survival: tuple[int, ...]) -> str:
  """(3,), (2, 3) -> "B3/S23"."""
  return "B" + "".join(str(n) for n in birth) + "/S" + "".join(str(n) for n in survival)


EXAMPLE_RULE = format_rule(DEFAULT_BIRTH, DEFAULT_SURVIVAL)


def parse_counts(digits: str) -> tuple[int, ...]:
  """The neighbor counts written after B or S, like "23" -> (2, 3). Order and repeats do not matter."""
  counts = set()
  for char in digits:
    if char not in "0123456789":
      raise ValueError(f"Only the digits 0-{MAX_NEIGHBORS} can follow B and S (found '{char}'). Example: {EXAMPLE_RULE}.")
    if int(char) > MAX_NEIGHBORS:
      raise ValueError(f"{char} is out of range: a cell has at most {MAX_NEIGHBORS} neighbors, so use 0-{MAX_NEIGHBORS}.")
    counts.add(int(char))
  return tuple(sorted(counts))


def parse_rule(text: str) -> tuple[tuple[int, ...], tuple[int, ...]]:
  """
  Turns a rule like "B3/S23" into ((3,), (2, 3)): birth counts first, then survival counts.
  Raises ValueError with a message the user can act on when the text does not follow the format.
  """
  rule = str(text).strip()
  if not rule:
    raise ValueError(f"Enter a rule like {EXAMPLE_RULE}.")
  if rule.count("/") != 1:
    raise ValueError(f"Separate birth and survival with one slash, like {EXAMPLE_RULE}.")

  birth_part, survival_part = rule.split("/")
  if birth_part[:1].upper() != "B":
    if birth_part[:1].upper() == "S" and survival_part[:1].upper() == "B":
      raise ValueError(f"Birth comes first, then survival, like {EXAMPLE_RULE}.")
    raise ValueError(f"The rule must start with B (birth), like {EXAMPLE_RULE}.")
  if survival_part[:1].upper() != "S":
    raise ValueError(f"After the slash comes S (survival), like {EXAMPLE_RULE}.")

  return parse_counts(birth_part[1:]), parse_counts(survival_part[1:])


def create_grid(size: int, random_fill: float = 0.0) -> list[list[int]]:
  return [
    [LIVE_CELL if random.random() < random_fill else DEAD_CELL for _ in range(size)]
    for _ in range(size)
  ]


def count_live_cells(grid: list[list[int]]) -> int:
  """Counts live cells between steps (when no cell is mid-change)."""
  return sum(row.count(LIVE_CELL) for row in grid)


class Game:
  """Holds everything about one game: grid, rules, generation, and the limit it stops at."""

  def __init__(self, size: int = DEFAULT_SIZE):
    self.birth = DEFAULT_BIRTH
    self.survival = DEFAULT_SURVIVAL
    self.max_generations = DEFAULT_MAX_GENERATIONS
    self._paint_value = None
    self._last_painted = None
    self.randomize(size)

  # --- state the page reads ---
  @property
  def live_cells(self) -> int:
    return count_live_cells(self.grid)

  @property
  def finished(self) -> bool:
    return self.generation >= self.max_generations

  @property
  def stop_reason(self) -> str:
    """Why the game cannot go on: "" (it can), "extinct" (no live cells), "stable" (nothing changes anymore) or "max"."""
    if self._halt:
      return self._halt
    return REASON_MAX if self.finished else ""

  @property
  def rule_text(self) -> str:
    return format_rule(self.birth, self.survival)

  def cells(self) -> bytes:
    """The grid flattened row by row, one byte per cell (DEAD_CELL or LIVE_CELL between steps)."""
    return b"".join(bytes(row) for row in self.grid)

  # --- settings ---
  def set_rule(self, text: str) -> str:
    """
    Sets the rule from text like "B3/S23". Blank text means the default rule.
    Returns "" on success, or a message about what is wrong (the old rule stays).
    """
    try:
      if not str(text).strip():
        new_birth, new_survival = DEFAULT_BIRTH, DEFAULT_SURVIVAL
      else:
        new_birth, new_survival = parse_rule(text)
    except ValueError as error:
      return str(error)
    self.birth, self.survival = new_birth, new_survival
    self._halt = ""  # a frozen grid may start moving again under different rules
    return ""

  def set_max_generations(self, value) -> None:
    try:
      self.max_generations = min(MAX_GENERATIONS, max(MIN_GENERATIONS, int(value)))
    except (TypeError, ValueError):
      self.max_generations = DEFAULT_MAX_GENERATIONS

  # --- changing the grid ---
  def _start_over(self) -> None:
    self.generation = 0
    self._halt = ""
    self.initial_grid = [row[:] for row in self.grid]

  def resize(self, size) -> None:
    """Replaces the grid with an empty size x size grid (always square)."""
    try:
      size = int(size)
    except (TypeError, ValueError):
      size = DEFAULT_SIZE
    self.size = min(MAX_SIZE, max(MIN_SIZE, size))
    self.grid = create_grid(self.size)
    self._start_over()

  def randomize(self, size=None) -> None:
    if size is None:
      size = self.size
    self.resize(size)
    self.grid = create_grid(self.size, RANDOM_FILL)
    self._start_over()

  def clear(self) -> None:
    self.grid = create_grid(self.size)
    self._start_over()

  def set_cell(self, row: int, col: int, alive: bool) -> None:
    """Lets the user draw cells, before or during the run."""
    if not (0 <= row < self.size and 0 <= col < self.size):
      return
    self.grid[row][col] = LIVE_CELL if alive else DEAD_CELL
    self._halt = ""  # the user changed the grid, so it may evolve again
    if self.generation == 0:
      # drawing before the run changes what "reset" goes back to
      self.initial_grid[row][col] = self.grid[row][col]

  def begin_paint(self, row: int, col: int) -> None:
    """Mouse down on a cell: the first cell decides whether this stroke draws (dead -> alive) or erases."""
    if not (0 <= row < self.size and 0 <= col < self.size):
      return
    self._paint_value = not is_alive(self.grid[row][col])
    self._last_painted = (row, col)
    self.set_cell(row, col, self._paint_value)

  def paint(self, row: int, col: int) -> None:
    """
    Mouse dragged over a cell during a stroke started with begin_paint. A fast drag jumps over cells
    between two mouse events, so every cell on the straight line from the last painted cell is painted too.
    """
    if self._paint_value is None or self._last_painted is None:
      return
    last_row, last_col = self._last_painted
    row = min(max(row, 0), self.size - 1)  # a drag that leaves the grid sticks to its edge
    col = min(max(col, 0), self.size - 1)
    steps = max(abs(row - last_row), abs(col - last_col))
    for step in range(1, steps + 1):
      line_row = last_row + round((row - last_row) * step / steps)
      line_col = last_col + round((col - last_col) * step / steps)
      if is_alive(self.grid[line_row][line_col]) != self._paint_value:
        self.set_cell(line_row, line_col, self._paint_value)
    self._last_painted = (row, col)

  def end_paint(self) -> None:
    self._paint_value = None
    self._last_painted = None

  # --- progression ---
  def step(self) -> bool:
    """
    Runs one generation. Returns False when it could not advance: the max generation was reached,
    or the grid no longer changes (then `stop_reason` says which). A step that changes nothing is
    not counted as a new generation. The step that kills the last cell does count; the game then
    reports "extinct" through `stop_reason`.
    """
    if self.stop_reason:
      return False

    changed_cells = process_next_generation(self.grid, self.birth, self.survival)
    if changed_cells == 0:
      self._halt = REASON_EXTINCT if self.live_cells == 0 else REASON_STABLE
      return False

    self.generation += 1
    if self.live_cells == 0:
      self._halt = REASON_EXTINCT
    return True

  def reset(self) -> None:
    """Goes back to the grid as it was before the run started."""
    self.grid = [row[:] for row in self.initial_grid]
    self.generation = 0
    self._halt = ""


# the one game the page talks to
game = Game()
