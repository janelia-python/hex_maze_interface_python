#!/usr/bin/env python3
import argparse
import csv
import datetime
import json
import time


class ControllerAdapter:
    def __init__(self, config):
        self.config = config
        # TODO: import your real host library here

    def connect(self):
        print("CONNECT (implement using your host API)")

    def disconnect(self):
        print("DISCONNECT")

    def move_prism(self, cluster, prism, position):
        print(f"MOVE cluster={cluster} prism={prism} pos={position}")
        # TODO: call your real move command

    def home_prism(self, cluster, prism):
        print(f"HOME cluster={cluster} prism={prism}")
        # TODO: call your real home command

    def get_position(self, cluster, prism):
        # TODO: return (xactual, xtarget, vactual)
        return (0, 0, 0)


class TortureTest:
    def __init__(self, adapter, cfg):
        self.adapter = adapter
        self.cfg = cfg

        self.clusters = cfg["clusters"]
        self.prisms_per_cluster = cfg["prisms_per_cluster"]

        self.farA = cfg["far_pos_A"]
        self.farB = cfg["far_pos_B"]
        self.near_home = cfg["near_home_offset"]

        self.small = cfg["small_move"]
        self.reversals = cfg["reversals"]

        self.delay = cfg["cycle_delay_s"]

        self.log_file = open(cfg["log_path"], "a", newline="")
        self.writer = csv.writer(self.log_file)

    def log(self, cluster, prism, event, value=""):
        try:
            x, xt, v = self.adapter.get_position(cluster, prism)
        except Exception:
            x = xt = v = ""
        self.writer.writerow(
            [datetime.datetime.utcnow().isoformat(), cluster, prism, event, value, x, xt, v]
        )
        self.log_file.flush()

    def prisms(self):
        for c in self.clusters:
            for p in range(self.prisms_per_cluster):
                yield c, p

    def cycle(self):

        # long moves
        for c, p in self.prisms():
            self.adapter.move_prism(c, p, self.farA)
            self.log(c, p, "move_farA", self.farA)
            time.sleep(self.delay)

        for c, p in self.prisms():
            self.adapter.move_prism(c, p, self.farB)
            self.log(c, p, "move_farB", self.farB)
            time.sleep(self.delay)

        # reversal chatter
        for c, p in self.prisms():
            for i in range(self.reversals):
                pos = self.small if i % 2 == 0 else -self.small
                self.adapter.move_prism(c, p, pos)
                self.log(c, p, "reversal", pos)
                time.sleep(self.delay)

        # near home
        for c, p in self.prisms():
            self.adapter.move_prism(c, p, self.near_home)
            self.log(c, p, "move_near_home", self.near_home)
            time.sleep(self.delay)

        for c, p in self.prisms():
            self.adapter.home_prism(c, p)
            self.log(c, p, "home_near")
            time.sleep(self.delay)

        # nudge
        for c, p in self.prisms():
            self.adapter.move_prism(c, p, self.small)
            self.log(c, p, "nudge", self.small)
            time.sleep(self.delay)

        # far-home homing
        for c, p in self.prisms():
            self.adapter.move_prism(c, p, self.farA)
            self.log(c, p, "move_far_before_home", self.farA)
            time.sleep(self.delay)

        for c, p in self.prisms():
            self.adapter.home_prism(c, p)
            self.log(c, p, "home_far")
            time.sleep(self.delay)

    def run(self):
        while True:
            print("Starting torture cycle")
            self.cycle()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.json")
    args = parser.parse_args()

    cfg = json.load(open(args.config))

    adapter = ControllerAdapter(cfg)
    adapter.connect()

    test = TortureTest(adapter, cfg)

    try:
        test.run()
    finally:
        adapter.disconnect()


if __name__ == "__main__":
    main()
