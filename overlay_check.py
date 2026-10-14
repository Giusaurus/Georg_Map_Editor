
#****************#
#overlay_check.py
#****************#

import math, os, yaml, rclpy, matplotlib
import matplotlib.pyplot as plt
import sys
from rclpy.node import Node
from sensor_msgs.msg import LaserScan
from nav_msgs.msg import Odometry
from rclpy.qos import qos_profile_sensor_data as q


matplotlib.use("Agg")

MAP = "/home/giu/georg_maps/Nav_Test_V3.yaml"
MAX_RANGE_PLOT = 20.0   # Strahlen ohne Treffer (range_max) werden ignoriert
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "overlay.png")

rclpy.init()
n = Node("overlay")
scan, odom = [], []
n.create_subscription(LaserScan, "scan", scan.append, q)
n.create_subscription(Odometry, "odom", odom.append, q)
while not (scan and odom):
    rclpy.spin_once(n, timeout_sec=0.5)
s, o = scan[-1], odom[-1]

p, ori = o.pose.pose.position, o.pose.pose.orientation
yaw = math.atan2(2 * (ori.w * ori.z + ori.x * ori.y), 1 - 2 * (ori.y ** 2 + ori.z ** 2))
roll = math.atan2(2 * (ori.w * ori.x + ori.y * ori.z), 1 - 2 * (ori.x ** 2 + ori.y ** 2))
pitch = math.asin(max(-1.0, min(1.0, 2 * (ori.w * ori.y - ori.z * ori.x))))
print(f"Roll: {math.degrees(roll):.1f} Grad, Pitch: {math.degrees(pitch):.1f} Grad")

data = yaml.safe_load(open(MAP))
start = next((ob["position"] for ob in data.get("objects", {}).values()
              if ob.get("type") == "start"), (0.0, 0.0))
rx, ry = p.x + float(start[0]), p.y + float(start[1])   # Pose im Kartenrahmen

xs, ys = [], []
for i, r in enumerate(s.ranges):
    if s.range_min <= r < MAX_RANGE_PLOT:
        a = yaw + s.angle_min + i * s.angle_increment
        xs.append(rx + r * math.cos(a))
        ys.append(ry + r * math.sin(a))

all_x, all_y = [], []
plt.figure(figsize=(9, 9))
for poly in data["polygons"]:
    rings = poly.get("parts") or [poly["points"]]
    for ring in rings:
        pts = ring + [ring[0]]
        px = [a for a, b in pts]
        py = [b for a, b in pts]
        all_x += px
        all_y += py
        plt.plot(px, py, "r-", linewidth=1)
    first = rings[0]
    cx = sum(a for a, b in first) / len(first)
    cy = sum(b for a, b in first) / len(first)
    plt.text(cx, cy, poly["name"], fontsize=6, color="red", ha="center")


for name, ob in data.get("objects", {}).items():
    x, y = float(ob["position"][0]), float(ob["position"][1])
    all_x.append(x)
    all_y.append(y)
    plt.plot(x, y, "m*", markersize=10)
    plt.text(x + 0.05, y + 0.05, f"{name} ({ob.get('type', '')})", fontsize=7, color="m")    


if len(sys.argv) > 1 and sys.argv[1] in data.get("objects", {}):
    gx, gy = map(float, data["objects"][sys.argv[1]]["position"])
    dist = math.hypot(gx - rx, gy - ry)
    plt.plot([rx, gx], [ry, gy], "k--", linewidth=1)
    print(f"Abstand zu {sys.argv[1]}: {dist * 100:.1f} cm")

plt.scatter(xs, ys, s=4, c="tab:blue", label="Lidar (Kartenrahmen)")
plt.plot(rx, ry, "g^", markersize=10, label="Roboter")
plt.arrow(rx, ry, 0.4 * math.cos(yaw), 0.4 * math.sin(yaw), color="g", width=0.02)

plt.xlim(min(all_x) - 0.5, max(all_x) + 0.5)
plt.ylim(min(all_y) - 0.5, max(all_y) + 0.5)
plt.gca().set_aspect("equal")
plt.grid(True, alpha=0.3)
plt.legend(loc="upper right")
plt.savefig(OUT, dpi=150)

print(f"{OUT} gespeichert")
print(f"Pose: x={rx:.2f} y={ry:.2f} yaw={math.degrees(yaw):.0f} Grad, Treffer: {len(xs)}")