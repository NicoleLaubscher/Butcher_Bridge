"""Render the simulated plan comparison figure from the production model."""

import sys
from decimal import Decimal
from io import BytesIO
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
from matplotlib import pyplot as plt
from matplotlib.ticker import FuncFormatter

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

from decision_engine import compare_plans
from demo_comparison import EVALUATED_ON, scenario_one, scenario_two


def main():
    scenarios = (("A + B group with C on baseline", scenario_one),
                 ("Two retailer pairs use different offers", scenario_two))
    results = [(title, compare_plans(*example(), as_of=EVALUATED_ON)[0]) for title, example in scenarios]
    costs = [
        [Decimal(summary["baseline_total"]), Decimal(summary["fixed"]["total_cost"]),
         Decimal(summary["optimised"]["total_cost"])]
        for _, summary in results
    ]
    maximum = float(max(max(values) for values in costs))
    with plt.rc_context({"font.family": "DejaVu Sans", "svg.fonttype": "none",
                         "svg.hashsalt": "butcherbridge-impact", "axes.spines.top": False,
                         "axes.spines.right": False, "text.color": "#152e36"}):
        fig, axes = plt.subplots(1, 2, figsize=(10, 4.7), sharey=True)
        fig.subplots_adjust(left=.12, right=.98, bottom=.24, top=.76, wspace=.22)
        fig.text(.12, .92, "SIMULATED  |  Estimated procurement cost", fontsize=17, weight="bold")
        fig.text(.12, .86, "Baseline, fixed-batch and optimised plans on the same inputs", fontsize=10)
        for index, (ax, (title, summary), values) in enumerate(zip(axes, results, costs, strict=True), 1):
            ax.set_title(f"Scenario {index} · {title}", fontsize=9, loc="left", weight="bold", pad=10)
            amounts = [float(value) for value in values]
            bars = ax.bar(range(3), amounts, width=.58, color=["#728b9b", "#276775", "#0c4854"])
            ax.bar_label(bars, labels=[f"R{value:,.0f}" for value in values], padding=4, fontsize=9)
            ax.set_xticks(range(3), ["Individual\nbaseline", "Fixed\nbatches", "Optimised\ngroups"], fontsize=9)
            ax.set_ylim(0, maximum * 1.19)
            ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"R{value/1000:.0f}k"))
            ax.set_axisbelow(True)
            ax.grid(axis="y", color="#dbe3e8", linewidth=.75)
            saving = Decimal(summary["incremental"]["savings_vs_fixed"])
            percent = summary["incremental"]["savings_pct_of_fixed"]
            ax.text(.5, -.32, f"Incremental estimated saving  R{saving:,.0f} ({percent}% of fixed)",
                    ha="center", transform=ax.transAxes, fontsize=8.5, weight="bold")
        fig.text(.12, .035, "ButcherBridge offline fixtures and current planner  ·  Projected costs in ZAR",
                 fontsize=8)
        svg = BytesIO()
        fig.savefig(svg, format="svg",
                    metadata={"Date": None, "Title": "Simulated ButcherBridge procurement cost comparison"})
        plt.close(fig)
    output = APP_DIR / "docs" / "diagrams" / "simulated_plan_costs.svg"
    output.write_bytes(b"\n".join(line.rstrip() for line in svg.getvalue().splitlines()) + b"\n")


if __name__ == "__main__":
    main()
