// One ECharts wrapper on echarts/core so only the chart types we use are bundled.
// useUTC: timestamps are plant-clock values parsed as UTC (lib/format.ts), so axes must not shift them to the browser timezone.
import { memo } from "react";
import ReactEChartsCore from "echarts-for-react/esm/core";
import * as echarts from "echarts/core";
import { BarChart, CustomChart, GaugeChart, HeatmapChart, LineChart } from "echarts/charts";
import { DataZoomComponent, GridComponent, MarkAreaComponent, MarkLineComponent, TooltipComponent, VisualMapComponent } from "echarts/components";
import { SVGRenderer } from "echarts/renderers";
import { echartsTheme } from "../theme";
import { reducedMotion } from "../components/ui";

echarts.use([BarChart, CustomChart, GaugeChart, HeatmapChart, LineChart, DataZoomComponent, GridComponent,
  MarkAreaComponent, MarkLineComponent, TooltipComponent, VisualMapComponent, SVGRenderer]);
echarts.registerTheme("dalmia", echartsTheme);

export type Option = echarts.EChartsCoreOption;

/** Memoised: a chart re-renders only when its own option/label changes. During Console playback the
 *  time-dependent charts still redraw each tick (by design); static ones on the page do not. */
export default memo(function Chart({ option, height = 280, label, onEvents, animate = true }: {
  option: Option; height?: number; label: string; onEvents?: Record<string, (p: never) => void>; animate?: boolean;
}) {
  return (
    <div role="img" aria-label={label}>
      <ReactEChartsCore echarts={echarts} theme="dalmia" option={{ useUTC: true, animation: animate && !reducedMotion(), animationDuration: 300, ...option }}
        style={{ height, width: "100%" }} opts={{ renderer: "svg" }} lazyUpdate onEvents={onEvents} />
    </div>
  );
});
