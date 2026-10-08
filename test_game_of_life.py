"""Run with: python3 -m unittest -v"""
import copy
import random
import unittest

import game_of_life as g


def reference_step(grid, birth, survival):
  """Plain copy-based Game of Life on 0/1 grids, to compare the in-place version against."""
  rows, cols = len(grid), len(grid[0])
  out = [[0] * cols for _ in range(rows)]
  for r in range(rows):
    for c in range(cols):
      n = sum(
        grid[a][b]
        for a in range(max(0, r - 1), min(rows, r + 2))
        for b in range(max(0, c - 1), min(cols, c + 2))
      ) - grid[r][c]
      out[r][c] = 1 if (grid[r][c] and n in survival) or (not grid[r][c] and n in birth) else 0
  return out


def alive_view(grid):
  return [[1 if g.is_alive(cell) else 0 for cell in row] for row in grid]


class RulesTest(unittest.TestCase):
  def test_in_place_matches_copy_based_reference(self):
    for _ in range(300):
      rows, cols = random.randint(1, 12), random.randint(1, 12)
      birth = g.parse_counts("".join(random.sample("012345678", random.randint(0, 4))))
      survival = g.parse_counts("".join(random.sample("012345678", random.randint(0, 5))))
      grid = [[random.randint(0, 1) for _ in range(cols)] for _ in range(rows)]
      expected = copy.deepcopy(grid)
      for _ in range(8):
        g.process_next_generation(grid, birth, survival)
        expected = reference_step(expected, birth, survival)
        self.assertEqual(alive_view(grid), expected)

  def test_only_plain_states_remain_after_a_step_and_changes_are_counted(self):
    grid = [[0, 0, 0], [1, 1, 1], [0, 0, 0]]  # blinker: 4 cells change
    self.assertEqual(g.process_next_generation(grid), 4)
    self.assertEqual(grid, [[0, 1, 0], [0, 1, 0], [0, 1, 0]])
    block = [[1, 1], [1, 1]]
    self.assertEqual(g.process_next_generation(block), 0)

  def test_neighbor_count_clips_at_the_edges(self):
    grid = [[1, 1, 1], [1, 1, 1], [1, 1, 1]]
    self.assertEqual(g.count_alive_neighbors(grid, 0, 0), 3)   # corner
    self.assertEqual(g.count_alive_neighbors(grid, 0, 1), 5)   # edge
    self.assertEqual(g.count_alive_neighbors(grid, 1, 1), 8)   # middle
    self.assertEqual(g.count_alive_neighbors(grid, 2, 2), 3)   # opposite corner (no wrap-around)

  def test_parse_rule(self):
    self.assertEqual(g.parse_rule("B3/S23"), ((3,), (2, 3)))
    self.assertEqual(g.parse_rule(" b36/s32 "), ((3, 6), (2, 3)))      # case, spaces around, and digit order don't matter
    self.assertEqual(g.parse_rule("B2/S"), ((2,), ()))                   # an empty list is allowed (Seeds)
    self.assertEqual(g.parse_rule("B3/S012345678")[1], tuple(range(9)))
    self.assertEqual(g.format_rule((3,), (2, 3)), "B3/S23")

  def test_parse_rule_errors_say_what_is_wrong(self):
    cases = {
      "": "Enter a rule",
      "B3S23": "slash",
      "B3/S2/3": "slash",
      "S23/B3": "Birth comes first",
      "23/3": "must start with B",
      "B3/23": "comes S",
      "B9/S23": "out of range",
      "B3/S29": "out of range",
      "B3/S2x": "found 'x'",
      "B3/S2 3": "found ' '",
    }
    for text, expected in cases.items():
      with self.assertRaises(ValueError, msg=text) as raised:
        g.parse_rule(text)
      self.assertIn(expected, str(raised.exception), msg=text)


class GameTest(unittest.TestCase):
  def draw(self, game, cells):
    game.clear()
    for row, col in cells:
      game.set_cell(row, col, True)

  def test_stable_grid_stops(self):
    game = g.Game(10)
    self.draw(game, [(2, 2), (2, 3), (3, 2), (3, 3)])  # block
    self.assertFalse(game.step())
    self.assertEqual((game.stop_reason, game.generation), (g.REASON_STABLE, 0))
    game.set_cell(8, 8, True)  # drawing lets it run again
    self.assertEqual(game.stop_reason, "")

  def test_blinker_never_stops_and_extinction_is_reported(self):
    game = g.Game(10)
    self.draw(game, [(1, 2), (2, 2), (3, 2)])
    for _ in range(10):
      self.assertTrue(game.step())
      self.assertEqual(game.stop_reason, "")
    for cell in [(1, 2), (2, 2), (3, 2)]:
      game.set_cell(*cell, False)
    self.assertFalse(game.step())
    self.assertEqual(game.stop_reason, g.REASON_EXTINCT)

  def test_lone_cell_dies(self):
    game = g.Game(10)
    self.draw(game, [(5, 5)])
    self.assertTrue(game.step())
    self.assertEqual((game.live_cells, game.stop_reason, game.generation), (0, g.REASON_EXTINCT, 1))

  def test_max_generations_and_reset(self):
    game = g.Game(10)
    self.draw(game, [(1, 2), (2, 2), (3, 2)])
    game.set_max_generations(3)
    self.assertEqual([game.step() for _ in range(4)], [True, True, True, False])
    self.assertEqual(game.stop_reason, g.REASON_MAX)
    game.set_cell(8, 8, True)  # drawn mid-run: not part of the starting grid
    game.reset()
    self.assertEqual((game.generation, game.live_cells, game.stop_reason), (0, 3, ""))
    game.set_max_generations(99999)
    self.assertEqual(game.max_generations, g.MAX_GENERATIONS)
    game.set_max_generations(-5)
    self.assertEqual(game.max_generations, g.MIN_GENERATIONS)
    game.set_max_generations("not a number")
    self.assertEqual(game.max_generations, g.DEFAULT_MAX_GENERATIONS)

  def test_settings_are_validated(self):
    game = g.Game()
    self.assertEqual(game.rule_text, "B3/S23")
    self.assertEqual(game.set_rule("B36/S23"), "")
    self.assertEqual(game.rule_text, "B36/S23")
    self.assertNotEqual(game.set_rule("B9/S23"), "")
    self.assertEqual(game.rule_text, "B36/S23")   # a bad rule leaves the old one in place
    game.resize(5000)
    self.assertEqual(game.size, g.MAX_SIZE)
    self.assertEqual((g.MAX_SIZE, g.DEFAULT_SIZE), (300, 100))
    game.resize(1)
    self.assertEqual(game.size, g.MIN_SIZE)
    game.resize("x")
    self.assertEqual(game.size, g.DEFAULT_SIZE)

  def test_paint_stroke_draws_or_erases_depending_on_first_cell(self):
    game = g.Game(10)
    game.clear()
    game.set_cell(0, 1, True)
    game.begin_paint(0, 0)   # starts on a dead cell: draws
    game.paint(0, 1)         # already alive, left alone
    game.paint(0, 2)
    game.end_paint()
    self.assertEqual(game.cells()[:3], bytes([1, 1, 1]))
    game.begin_paint(0, 0)   # starts on a live cell: erases
    game.paint(0, 1)
    game.end_paint()
    game.paint(0, 2)         # no stroke in progress: ignored
    self.assertEqual(game.cells()[:3], bytes([0, 0, 1]))

  def test_fast_drag_fills_the_cells_it_jumped_over(self):
    game = g.Game(10)
    game.clear()
    game.begin_paint(1, 1)
    game.paint(1, 6)    # the mouse jumped five cells in one event
    game.paint(4, 9)    # diagonal jump
    game.end_paint()
    row = lambda r: list(game.cells()[r * 10:(r + 1) * 10])
    self.assertEqual(row(1), [0, 1, 1, 1, 1, 1, 1, 0, 0, 0])
    self.assertEqual([game.cells()[r * 10 + c] for r, c in [(2, 7), (3, 8), (4, 9)]], [1, 1, 1])
    game.begin_paint(1, 1)   # erasing works the same way
    game.paint(1, 6)
    game.end_paint()
    self.assertEqual(row(1), [0] * 10)

  def test_randomize_fills_about_a_fifth(self):
    game = g.Game(100)
    self.assertTrue(0.15 < game.live_cells / 10000 < 0.25)
    self.assertEqual(g.DEFAULT_MAX_GENERATIONS, 250)

  def test_omitted_inputs_fall_back_to_the_defaults(self):
    game = g.Game()
    game.set_rule("B2/S")
    for blank in ("", "   "):
      self.assertEqual(game.set_rule(blank), "")
      self.assertEqual(game.rule_text, "B3/S23")
      game.set_rule("B2/S")
    for blank in ("", None, "   ", "abc"):
      game.set_max_generations(5)
      game.set_max_generations(blank)
      self.assertEqual(game.max_generations, g.DEFAULT_MAX_GENERATIONS)
      game.randomize(10)
      game.resize(blank)
      self.assertEqual(game.size, g.DEFAULT_SIZE)

  def test_generation_limit_is_kept_in_range(self):
    game = g.Game()
    game.set_max_generations(99999)
    self.assertEqual(game.max_generations, g.MAX_GENERATIONS)
    game.set_max_generations(0)
    self.assertEqual(game.max_generations, g.MIN_GENERATIONS)
    game.set_max_generations("12")
    self.assertEqual(game.max_generations, 12)

  def test_new_rule_lets_a_frozen_grid_move_again(self):
    game = g.Game(10)
    game.clear()
    for cell in [(2, 2), (2, 3), (3, 2), (3, 3)]:   # block: stable under B3/S23
      game.set_cell(*cell, True)
    self.assertFalse(game.step())
    self.assertEqual(game.stop_reason, g.REASON_STABLE)
    self.assertEqual(game.set_rule("B3/S"), "")     # without survival the block dies
    self.assertEqual(game.stop_reason, "")
    self.assertTrue(game.step())
    self.assertEqual((game.live_cells, game.stop_reason), (0, g.REASON_EXTINCT))

  def test_randomize_and_clear(self):
    game = g.Game(10)
    game.randomize(20)
    self.assertEqual((game.size, len(game.cells()), game.generation), (20, 400, 0))
    game.set_cell(0, 0, True)
    game.randomize()                      # no size given: keeps the current one
    self.assertEqual(game.size, 20)
    self.assertEqual(g.count_live_cells(g.create_grid(5, 1.0)), 25)   # fill chance 1 = all alive
    self.assertEqual(g.count_live_cells(g.create_grid(5)), 0)
    game.step()
    game.clear()
    self.assertEqual((game.live_cells, game.generation, game.stop_reason, game.size), (0, 0, "", 20))

  def test_resize_starts_over(self):
    game = g.Game(10)
    game.step()
    game.resize(15)
    self.assertEqual((game.size, game.live_cells, game.generation), (15, 0, 0))

  def test_cells_outside_the_grid_are_ignored(self):
    game = g.Game(10)
    game.clear()
    for row, col in [(-1, 0), (0, -1), (10, 0), (0, 10)]:
      game.set_cell(row, col, True)
      game.begin_paint(row, col)
      game.end_paint()
    self.assertEqual(game.live_cells, 0)

  def test_drawing_before_the_run_changes_what_reset_goes_back_to(self):
    game = g.Game(10)
    game.clear()
    game.set_cell(4, 4, True)
    game.step()                       # lone cell dies
    game.reset()
    self.assertEqual(game.live_cells, 1)
    self.assertEqual(game.generation, 0)

  def test_drag_that_leaves_the_grid_sticks_to_the_edge(self):
    game = g.Game(10)
    game.clear()
    game.begin_paint(5, 7)
    game.paint(5, 40)                 # pointer went far past the right edge
    game.end_paint()
    self.assertEqual(list(game.cells()[50:60]), [0] * 7 + [1, 1, 1])

  def test_is_alive_counts_cells_about_to_die(self):
    self.assertEqual([g.is_alive(s) for s in (g.DEAD_CELL, g.LIVE_CELL, g.WILL_BE_ALIVE, g.WILL_BE_DEAD)],
                     [False, True, False, True])

  def test_finished_follows_the_generation_limit(self):
    game = g.Game(10)
    game.clear()
    for cell in [(1, 2), (2, 2), (3, 2)]:
      game.set_cell(*cell, True)
    game.set_max_generations(2)
    self.assertFalse(game.finished)
    game.step(); game.step()
    self.assertTrue(game.finished)
    self.assertEqual(game.stop_reason, g.REASON_MAX)


if __name__ == "__main__":
  unittest.main()
