"""
Prometheus metrics
==================

`/metrics` in the Prometheus text format. Almost everything is read at scrape
time from the stats the engine already keeps (one custom collector), so the
hot paths carry no instrumentation. The one exception is the feed latency
histogram, observed once per market event (a few microseconds).

Exported (all prefixed `algoviz_`):

- event loop: lag p50 / p99 / max
- feed: events, trades, diffs and dropped diffs (counters), event rate, book
  resyncs, feed latency (local receive − exchange event time, so it includes
  the clock offset between the two)
- WebSocket: clients, frames sent and dropped, per-client backlog
- persistence: bars written, failed flushes (bars and predictions), prediction
  backlog
- ML: training duration, inference latency, inference timeouts, training runs,
  model version
- backtests running or queued; alerts evaluated and fired; DB errors
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

from prometheus_client import CollectorRegistry, Histogram
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily
from prometheus_client.registry import Collector

FEED_LATENCY = Histogram(
    "algoviz_feed_latency_ms",
    "Local receive time minus exchange event time, per market event (includes clock offset)",
    ["symbol"],
    buckets=(5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000),
    registry=None,  # registered in the app's own registry (build_registry), not the global one
)


class EngineCollector(Collector):
    """Reads `/system/metrics`-style stats and yields metric families at scrape time."""

    def __init__(self, stats: Callable[[], dict[str, Any]]) -> None:
        self._stats = stats

    def collect(self) -> Iterator[Any]:
        s = self._stats()
        market, ws, loop = s["market"], s["ws"], s["loop"]

        lag = GaugeMetricFamily(
            "algoviz_event_loop_lag_ms", "Event-loop lag over the last minute", labels=["quantile"]
        )
        for q, key in (("0.5", "p50_ms"), ("0.99", "p99_ms"), ("1", "max_ms")):
            if loop.get(key) is not None:
                lag.add_metric([q], loop[key])
        yield lag

        counters = {
            "events": ("algoviz_feed_events_total", "Market events processed"),
            "trades": ("algoviz_feed_trades_total", "Trades processed"),
            "diffs": ("algoviz_feed_diffs_total", "Depth diffs processed"),
            "dropped_diffs": (
                "algoviz_feed_dropped_diffs_total",
                "Depth diffs dropped (gaps and resyncs)",
            ),
            "bars_closed": ("algoviz_bars_closed_total", "1-second bars closed"),
        }
        families = {
            k: CounterMetricFamily(name, doc, labels=["symbol"])
            for k, (name, doc) in counters.items()
        }
        rate = GaugeMetricFamily(
            "algoviz_feed_event_rate", "Market events per second", labels=["symbol"]
        )
        resyncs = CounterMetricFamily(
            "algoviz_book_resyncs_total", "Order-book resynchronisations", labels=["symbol"]
        )
        connected = GaugeMetricFamily(
            "algoviz_feed_connected", "1 while the market feed is connected", labels=["symbol"]
        )
        train_s = GaugeMetricFamily(
            "algoviz_ml_last_training_seconds",
            "Duration of the last training run",
            labels=["symbol"],
        )
        infer_ms = GaugeMetricFamily(
            "algoviz_ml_last_inference_ms", "Latency of the last prediction", labels=["symbol"]
        )
        timeouts = CounterMetricFamily(
            "algoviz_ml_inference_timeouts_total",
            "Predictions skipped for exceeding the timeout",
            labels=["symbol"],
        )
        version = GaugeMetricFamily(
            "algoviz_ml_model_version",
            "Version of the served model (0: none yet)",
            labels=["symbol"],
        )
        backlog = GaugeMetricFamily(
            "algoviz_prediction_backlog",
            "Predictions and resolutions waiting to be written",
            labels=["symbol"],
        )
        pred_fail = CounterMetricFamily(
            "algoviz_prediction_failed_flushes_total",
            "Prediction writes that failed (and were re-queued)",
            labels=["symbol"],
        )
        for sym, e in market["symbols"].items():
            for key, fam in families.items():
                fam.add_metric([sym], e[key])
            rate.add_metric([sym], e["event_rate_per_s"])
            resyncs.add_metric([sym], e["book"]["resyncs"])
            connected.add_metric([sym], 1.0 if e["connected"] else 0.0)
            ml = e.get("ml")
            if ml:
                if ml.get("last_training_s") is not None:
                    train_s.add_metric([sym], ml["last_training_s"])
                if ml.get("last_inference_ms") is not None:
                    infer_ms.add_metric([sym], ml["last_inference_ms"])
                timeouts.add_metric([sym], ml["inference_timeouts"])
                version.add_metric([sym], ml["version"])
                backlog.add_metric([sym], ml["prediction_backlog"])
                pred_fail.add_metric([sym], ml["prediction_failed_flushes"])
        yield from families.values()
        yield from (
            rate,
            resyncs,
            connected,
            train_s,
            infer_ms,
            timeouts,
            version,
            backlog,
            pred_fail,
        )

        writer = market["writer"]
        yield CounterMetricFamily(
            "algoviz_bars_written_total", "Bars persisted", value=writer["written"]
        )
        yield CounterMetricFamily(
            "algoviz_bar_failed_flushes_total",
            "Bar writes that failed (and were re-queued)",
            value=writer["failed_flushes"],
        )
        yield GaugeMetricFamily(
            "algoviz_bar_writer_queue", "Bars waiting to be written", value=writer.get("queued", 0)
        )
        yield CounterMetricFamily(
            "algoviz_db_errors_total",
            "Failed database writes (bars and predictions)",
            value=writer["failed_flushes"]
            + sum(
                (e.get("ml") or {}).get("prediction_failed_flushes", 0)
                for e in market["symbols"].values()
            ),
        )

        yield GaugeMetricFamily(
            "algoviz_ws_clients", "Connected WebSocket clients", value=ws["clients"]
        )
        yield CounterMetricFamily(
            "algoviz_ws_frames_sent_total", "WebSocket frames sent", value=ws["total_sent"]
        )
        yield CounterMetricFamily(
            "algoviz_ws_frames_dropped_total",
            "Frames dropped by per-client backpressure",
            value=sum(c["dropped"] for c in ws["per_client"]),
        )
        yield GaugeMetricFamily(
            "algoviz_ws_backlog_max",
            "Largest per-client send backlog",
            value=max((c["backlog"] for c in ws["per_client"]), default=0),
        )

        alerts = market["alerts"]
        yield CounterMetricFamily(
            "algoviz_alert_evaluations_total", "Alert rule evaluations", value=alerts["evaluations"]
        )
        yield CounterMetricFamily(
            "algoviz_alerts_fired_total", "Alerts fired", value=alerts["fired"]
        )
        yield GaugeMetricFamily(
            "algoviz_backtests_active",
            "Backtests running or queued",
            value=len(market["backtests_running"]),
        )


def build_registry(stats: Callable[[], dict[str, Any]]) -> CollectorRegistry:
    """A registry with the engine collector and the process-wide latency histogram."""
    registry = CollectorRegistry(auto_describe=False)
    registry.register(EngineCollector(stats))
    registry.register(FEED_LATENCY)
    return registry
