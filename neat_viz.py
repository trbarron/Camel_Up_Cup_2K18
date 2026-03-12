"""
neat_viz.py — NEAT topology visualiser for NeatCamel.

Draws the best genome as a layered directed graph:
  - Input nodes on the left, labelled with feature names
  - Output nodes on the right, labelled with action names
  - Hidden nodes distributed in the middle
  - Connections: blue = positive weight, red = negative weight
                 opacity and thickness scale with |weight|
                 dashed = disabled connection

Usage (standalone):
    python neat_viz.py                             # load neat_best_genome.pkl
    python neat_viz.py path/to/genome.pkl          # specific genome
    python neat_viz.py --out topology.png          # custom output path

Called from train_neat.py via draw_topology(genome, config, path, title).
"""

import os
import sys

# ── Feature / action labels ───────────────────────────────────────────────────

INPUT_LABELS = [
    # camel positions (normalised)
    "pos0", "pos1", "pos2", "pos3", "pos4",
    # camel stack heights
    "stk0", "stk1", "stk2", "stk3", "stk4",
    # yet-to-move flags
    "ytm0", "ytm1", "ytm2", "ytm3", "ytm4",
    # player money (normalised)
    "mon0", "mon1", "mon2", "mon3",
    # relative money vs me
    "rel1", "rel2", "rel3",
    # round bets placed per camel
    "rbt0", "rbt1", "rbt2", "rbt3", "rbt4",
    # game bet already placed per camel
    "gbt0", "gbt1", "gbt2", "gbt3", "gbt4",
    # aggregate bet counts
    "gwb", "glb",
    # trap placed
    "trap",
    # derived features
    "lead", "spread", "rndStg", "rank",
]

OUTPUT_LABELS = [
    "Roll",
    "Rnd0", "Rnd1", "Rnd2", "Rnd3", "Rnd4",
    "Win0", "Win1", "Win2", "Win3", "Win4",
    "Los0", "Los1", "Los2", "Los3", "Los4",
]

# Group colours for input nodes (same order as INPUT_LABELS)
_INPUT_GROUPS = (
    ("#4caf50", 5),   # camel positions — green
    ("#8bc34a", 5),   # camel stack    — light green
    ("#03a9f4", 5),   # yet-to-move    — blue
    ("#ff9800", 4),   # player money   — orange
    ("#ff5722", 3),   # relative money — deep orange
    ("#9c27b0", 5),   # round bets     — purple
    ("#e91e63", 5),   # game bets      — pink
    ("#607d8b", 2),   # agg bets       — grey-blue
    ("#795548", 1),   # trap           — brown
    ("#00bcd4", 4),   # derived        — teal
)

# Group colours for output nodes
_OUTPUT_GROUPS = (
    ("#f44336", 1),   # Roll  — red
    ("#ffeb3b", 5),   # Round bets — yellow
    ("#2196f3", 5),   # Win bets  — blue
    ("#9c27b0", 5),   # Lose bets — purple
)


def _node_colours(labels, groups):
    colours = []
    for colour, count in groups:
        colours.extend([colour] * count)
    # Pad / truncate to match labels length
    while len(colours) < len(labels):
        colours.append("#90a4ae")
    return colours[:len(labels)]


# ── Core draw function ────────────────────────────────────────────────────────

def draw_topology(genome, config, filename="neat_topology.png", title=""):
    """
    Render *genome* as a layered directed graph and save to *filename*.

    Parameters
    ----------
    genome   : neat DefaultGenome
    config   : neat Config
    filename : output image path (PNG / SVG / PDF supported by matplotlib)
    title    : extra text appended to the figure title
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
        from matplotlib.lines import Line2D
    except ImportError:
        print("[neat_viz] matplotlib not installed — skipping topology plot.")
        return

    gc          = config.genome_config
    input_keys  = gc.input_keys   # e.g. [-1, -2, ..., -35]  (most negative = input 0)
    output_keys = gc.output_keys  # [0, 1, ..., 15]
    hidden_keys = sorted(
        k for k in genome.nodes if k not in output_keys
    )

    n_in  = len(input_keys)
    n_out = len(output_keys)
    n_hid = len(hidden_keys)

    # ── Node positions ────────────────────────────────────────────────────────
    # x: inputs=0.0, hidden distributed in (0.15, 0.85), outputs=1.0
    # y: evenly spaced 0→1 within each column

    def _col(count, x):
        if count == 1:
            return [(x, 0.5)]
        return [(x, i / (count - 1)) for i in range(count)]

    pos = {}

    # Inputs: input_keys are negative; key -1 is the LAST feature in neat-python
    # neat assigns input keys as -(num_inputs) … -1 so key[0] = -(num_inputs) = feature 0
    for i, k in enumerate(sorted(input_keys)):   # sorted: most negative first → feature 0 first
        pos[k] = (0.0, i / (n_in - 1) if n_in > 1 else 0.5)

    for i, k in enumerate(output_keys):
        pos[k] = (1.0, i / (n_out - 1) if n_out > 1 else 0.5)

    if n_hid > 0:
        # Rough x placement: try to push each hidden node right based on which
        # outputs it (transitively) connects to — simple heuristic: average x of
        # its direct neighbors, clamped to (0.2, 0.8).
        hid_x = {}
        for k in hidden_keys:
            nbrs = []
            for (a, b) in genome.connections:
                if a == k and b in pos:
                    nbrs.append(pos[b][0])
                if b == k and a in pos:
                    nbrs.append(pos[a][0])
            hid_x[k] = max(0.2, min(0.8, (sum(nbrs) / len(nbrs)) if nbrs else 0.5))

        # Spread nodes with the same x vertically
        from collections import defaultdict
        by_x = defaultdict(list)
        for k in hidden_keys:
            by_x[round(hid_x[k], 1)].append(k)
        for x_val, ks in by_x.items():
            for j, k in enumerate(ks):
                pos[k] = (x_val, j / (len(ks) - 1) if len(ks) > 1 else 0.5)

    # ── Figure setup ──────────────────────────────────────────────────────────
    fig_h = max(10, max(n_in, n_out) * 0.35)
    fig, ax = plt.subplots(figsize=(18, fig_h))
    ax.set_xlim(-0.12, 1.12)
    ax.set_ylim(-0.04, 1.04)
    ax.axis("off")

    # ── Draw connections ──────────────────────────────────────────────────────
    w_max = max((abs(c.weight) for c in genome.connections.values()), default=1.0)
    w_max = max(w_max, 1e-6)

    for (a, b), conn in genome.connections.items():
        if a not in pos or b not in pos:
            continue
        x1, y1 = pos[a]
        x2, y2 = pos[b]
        alpha = 0.15 + 0.75 * min(abs(conn.weight) / w_max, 1.0)
        lw    = 0.4 + 2.0  * min(abs(conn.weight) / w_max, 1.0)
        color = "#1565c0" if conn.weight >= 0 else "#c62828"
        ls    = "-" if conn.enabled else ":"
        ax.plot(
            [x1, x2], [y1, y2],
            color=color, alpha=alpha, linewidth=lw, linestyle=ls, zorder=1,
        )

    # ── Draw nodes ────────────────────────────────────────────────────────────
    node_r = 0.012

    in_colours  = _node_colours(INPUT_LABELS,  _INPUT_GROUPS)
    out_colours = _node_colours(OUTPUT_LABELS, _OUTPUT_GROUPS)

    # Inputs
    for i, k in enumerate(sorted(input_keys)):
        x, y = pos[k]
        circle = plt.Circle((x, y), node_r, color=in_colours[i],
                             ec="white", linewidth=0.5, zorder=3)
        ax.add_patch(circle)
        lbl = INPUT_LABELS[i] if i < len(INPUT_LABELS) else str(k)
        ax.text(x - 0.015, y, lbl, ha="right", va="center",
                fontsize=5.5, color="#333333", zorder=4)

    # Outputs
    for i, k in enumerate(output_keys):
        x, y = pos[k]
        circle = plt.Circle((x, y), node_r, color=out_colours[i],
                             ec="white", linewidth=0.5, zorder=3)
        ax.add_patch(circle)
        lbl = OUTPUT_LABELS[i] if i < len(OUTPUT_LABELS) else str(k)
        ax.text(x + 0.015, y, lbl, ha="left", va="center",
                fontsize=6.5, fontweight="bold", color="#111111", zorder=4)

    # Hidden
    for k in hidden_keys:
        if k not in pos:
            continue
        x, y = pos[k]
        circle = plt.Circle((x, y), node_r * 1.3, color="#ffcc02",
                             ec="white", linewidth=0.8, zorder=3)
        ax.add_patch(circle)
        ax.text(x, y, str(k), ha="center", va="center",
                fontsize=4.5, color="#333333", zorder=4)

    # ── Legend ────────────────────────────────────────────────────────────────
    legend_elements = [
        Line2D([0], [0], color="#1565c0", lw=1.5, label="positive weight"),
        Line2D([0], [0], color="#c62828", lw=1.5, label="negative weight"),
        Line2D([0], [0], color="#888888", lw=1.0, ls=":", label="disabled"),
        mpatches.Patch(color="#ffcc02", label="hidden node"),
    ]
    ax.legend(handles=legend_elements, loc="upper center",
              fontsize=7, ncol=4, framealpha=0.8,
              bbox_to_anchor=(0.5, 1.02))

    # ── Stats annotation ──────────────────────────────────────────────────────
    enabled  = sum(1 for c in genome.connections.values() if c.enabled)
    disabled = len(genome.connections) - enabled
    stats = (
        f"nodes={len(genome.nodes)}  "
        f"connections={enabled} enabled / {disabled} disabled  "
        f"fitness={genome.fitness:.2f}" if genome.fitness is not None
        else f"nodes={len(genome.nodes)}  connections={enabled}+{disabled}"
    )
    fig.text(0.5, 0.005, stats, ha="center", fontsize=7, color="#555555")

    title_str = f"NeatCamel topology"
    if title:
        title_str += f"  —  {title}"
    fig.suptitle(title_str, fontsize=11, fontweight="bold", y=1.005)

    plt.tight_layout(rect=[0, 0.015, 1, 1])
    os.makedirs(os.path.dirname(os.path.abspath(filename)), exist_ok=True)
    plt.savefig(filename, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"[neat_viz] topology → {filename}")


# ── Standalone entry point ────────────────────────────────────────────────────

def _main():
    import argparse, pickle

    _DIR = os.path.dirname(os.path.abspath(__file__))

    parser = argparse.ArgumentParser(description="Render a NeatCamel genome topology")
    parser.add_argument("genome", nargs="?",
                        default=os.path.join(_DIR, "neat_best_genome.pkl"),
                        help="Path to genome .pkl (default: neat_best_genome.pkl)")
    parser.add_argument("--config", default=os.path.join(_DIR, "neat_config.txt"))
    parser.add_argument("--out",    default=os.path.join(_DIR, "neat_topology.png"))
    args = parser.parse_args()

    try:
        import neat
    except ImportError:
        sys.exit("neat-python not installed: pip install neat-python")

    if not os.path.exists(args.genome):
        sys.exit(f"Genome not found: {args.genome}")

    config = neat.Config(
        neat.DefaultGenome, neat.DefaultReproduction,
        neat.DefaultSpeciesSet, neat.DefaultStagnation,
        args.config,
    )
    with open(args.genome, "rb") as f:
        genome = pickle.load(f)

    draw_topology(genome, config, args.out, title="best genome")
    print(f"Saved → {args.out}")


if __name__ == "__main__":
    _main()
