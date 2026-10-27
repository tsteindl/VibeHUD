"""Dummy training loop that logs to TensorBoard, to exercise the VibeHUD display.

    pip install tensorboardX        # or have torch installed
    python examples/tensorboard_dummy.py --logdir runs/dummy-1 --steps 3000 --sps 15

It writes train loss, validation loss (every 50 steps), a learning rate and an accuracy. Nothing here knows about VibeHUD:
any script that writes TensorBoard events looks the same to the agent.
"""
import argparse, math, os, random, time

try:
    from torch.utils.tensorboard import SummaryWriter
except ImportError:
    from tensorboardX import SummaryWriter

p = argparse.ArgumentParser()
p.add_argument("--logdir", default="runs/dummy-1")
p.add_argument("--steps", type=int, default=3000)
p.add_argument("--sps", type=float, default=15, help="steps per second")
args = p.parse_args()

os.makedirs(args.logdir, exist_ok=True)
# flush_secs=1: the default (120 s) would delay everything the display shows by up to two minutes.
writer = SummaryWriter(args.logdir, flush_secs=1)
random.seed(0)
writer.add_scalar("vibehud/total_steps", args.steps, 0)      # optional: progress % and ETA
for step in range(args.steps + 1):
    loss = 0.15 + 2.0 * math.exp(-step / (args.steps / 4)) + random.gauss(0, 0.02)
    writer.add_scalar("train/loss", loss, step)
    if step % 50 == 0:      # validation loss is logged less often than train loss, like once per epoch
        writer.add_scalar("val/loss", loss + 0.10 + 0.25 * step / args.steps + random.gauss(0, 0.02), step)
    writer.add_scalar("train/lr", 1e-3 * (1 - step / args.steps), step)
    writer.add_scalar("val/acc", 1 - 0.6 * math.exp(-step / (args.steps / 3)), step)
    time.sleep(1 / args.sps)
writer.close()
print("done")
