import { LineChart, SimpleBarChart } from "@carbon/charts-react";
import type { MetricPoint } from "../api";
import { histogramRows } from "../format";
import { useTheme } from "../theme";

type Series = { label: string; pick: (p: MetricPoint) => number | null };

/** Time-series line chart over the live metrics window. Animations off (low-motion product UI). */
export function TimeChart({ title, points, series, unit }: { title: string; points: MetricPoint[]; series: Series[]; unit: string }) {
  const { theme } = useTheme();
  const data = points.flatMap((p) =>
    series.flatMap((s) => {
      const v = s.pick(p);
      return v == null ? [] : [{ group: s.label, date: new Date(p.t * 1000), value: v }];
    }),
  );
  return (
    <LineChart
      data={data}
      options={{
        title, theme, height: "230px", animations: false, toolbar: { enabled: false }, points: { enabled: false },
        curve: "curveMonotoneX", legend: { position: "bottom", clickable: true },
        axes: {
          bottom: { mapsTo: "date", scaleType: "time" as never, ticks: { number: 5 } },
          left: { mapsTo: "value", title: unit, scaleType: "linear" as never },
        },
      }}
    />
  );
}

export function ScoreHistogram({ edges, counts }: { edges: number[]; counts: number[] }) {
  const { theme } = useTheme();
  return (
    <SimpleBarChart
      data={histogramRows(edges, counts)}
      options={{
        title: "Alert score relative to its threshold", theme, height: "230px", animations: false, toolbar: { enabled: false },
        legend: { enabled: false },
        axes: {
          left: { mapsTo: "value", title: "Alerts", scaleType: "linear" as never },
          bottom: { mapsTo: "key", title: "Score divided by threshold (1.0 = at the threshold)", scaleType: "labels" as never },
        },
      }}
    />
  );
}
