"""Phase 0: the program boots into its main loop and the raster IRQ paces it at 50 Hz."""

import unittest

from vice import Vice


class BootTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vm = Vice()
        cls.vm.run_to("frame_done")

    @classmethod
    def tearDownClass(cls):
        cls.vm.close()

    def test_reaches_main_loop(self):
        regs = self.vm.run_frames(1)
        self.assertEqual(regs["PC"], self.vm.addr("frame_done"))

    def test_memory_config(self):
        self.assertEqual(self.vm.peek8(0x01) & 0x07, 0x06)     # BASIC out, KERNAL + I/O in

    def test_pal(self):
        width, height, *_ = self.vm.display()
        self.assertEqual(height, 312)                          # PAL: 312 lines = 50 frames/s

    def test_one_frame_per_irq(self):
        before = self.vm.peek16("frame_counter")
        self.vm.run_frames(50)
        self.assertEqual(self.vm.peek16("frame_counter") - before, 50)

    def test_irq_at_fixed_line(self):
        lines = set()
        for _ in range(5):
            regs = self.vm.run_to("irq_top")
            lines.add(regs["LIN"])
        self.assertEqual(len(lines), 1, lines)
        self.assertLess(lines.pop(), 3)                        # top of the frame


if __name__ == "__main__":
    unittest.main()
