#!/usr/bin/env python3
"""Privacy-bounded population evidence and maintenance-window recommendations."""

import contextlib
import datetime
import json
import math
import os
import pathlib
import sqlite3
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


SCHEMA_VERSION = 1
DEFAULT_POLICY = {
    "schemaVersion": SCHEMA_VERSION,
    "timezone": "America/Regina",
    "lookbackDays": 28,
    "retentionDays": 90,
    "horizonDays": 7,
    "bucketSeconds": 300,
    "slotMinutes": 30,
    "durationMinutes": 30,
    "eligibleLocalStart": "02:00",
    "eligibleLocalEnd": "09:00",
    "defaultLocalTime": "06:00",
    "minimumNoticeMinutes": 30,
    "minimumWindowCoverage": 0.8,
    "minimumSampleDays": 2,
    "weekdayWeightingMinimumDays": 2,
    "recommendationCount": 8,
}


def _integer(value, name, minimum, maximum):
    try:
        value = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"maintenance planner {name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"maintenance planner {name} must be between {minimum} and {maximum}")
    return value


def _clock(value, name):
    text = str(value or "").strip()
    try:
        hour, minute = (int(part) for part in text.split(":"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"maintenance planner {name} must be HH:MM") from exc
    if not 0 <= hour <= 23 or not 0 <= minute <= 59 or text != f"{hour:02d}:{minute:02d}":
        raise ValueError(f"maintenance planner {name} must be HH:MM")
    return hour * 60 + minute


def load_policy(path):
    raw = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schemaVersion") != SCHEMA_VERSION:
        raise ValueError(f"maintenance planner policy schemaVersion must be {SCHEMA_VERSION}")
    unknown = set(raw) - set(DEFAULT_POLICY)
    if unknown:
        raise ValueError(f"maintenance planner policy has unknown keys: {sorted(unknown)}")
    policy = {**DEFAULT_POLICY, **raw}
    try:
        ZoneInfo(str(policy["timezone"]))
    except ZoneInfoNotFoundError as exc:
        raise ValueError("maintenance planner timezone is unknown") from exc
    for key, bounds in {
        "lookbackDays": (7, 365), "retentionDays": (30, 730), "horizonDays": (1, 30),
        "bucketSeconds": (60, 3600), "slotMinutes": (5, 180), "durationMinutes": (5, 360),
        "minimumNoticeMinutes": (1, 10080), "minimumSampleDays": (1, 60),
        "weekdayWeightingMinimumDays": (1, 20), "recommendationCount": (1, 50),
    }.items():
        policy[key] = _integer(policy[key], key, *bounds)
    if 86400 % policy["bucketSeconds"]:
        raise ValueError("maintenance planner bucketSeconds must divide one day")
    if policy["durationMinutes"] % (policy["bucketSeconds"] // 60):
        raise ValueError("maintenance planner durationMinutes must align to bucketSeconds")
    policy["eligibleStartMinute"] = _clock(policy["eligibleLocalStart"], "eligibleLocalStart")
    policy["eligibleEndMinute"] = _clock(policy["eligibleLocalEnd"], "eligibleLocalEnd")
    policy["defaultMinute"] = _clock(policy["defaultLocalTime"], "defaultLocalTime")
    if policy["eligibleStartMinute"] >= policy["eligibleEndMinute"]:
        raise ValueError("maintenance planner eligible window must not cross midnight")
    if policy["eligibleStartMinute"] + policy["durationMinutes"] > policy["eligibleEndMinute"]:
        raise ValueError("maintenance planner eligible window is shorter than durationMinutes")
    if not policy["eligibleStartMinute"] <= policy["defaultMinute"] <= policy["eligibleEndMinute"] - policy["durationMinutes"]:
        raise ValueError("maintenance planner defaultLocalTime must fit inside the eligible window")
    coverage = float(policy["minimumWindowCoverage"])
    if not 0.5 <= coverage <= 1.0:
        raise ValueError("maintenance planner minimumWindowCoverage must be between 0.5 and 1.0")
    policy["minimumWindowCoverage"] = coverage
    return policy


def _iso(epoch):
    return datetime.datetime.fromtimestamp(float(epoch), datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _percentile(values, percentile):
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    index = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return ordered[index]


class Store:
    def __init__(self, path, policy_path):
        self.path = pathlib.Path(path)
        self.policy_path = pathlib.Path(policy_path)

    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("pragma busy_timeout=30000")
        return connection

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with contextlib.closing(self._connect()) as connection, connection:
            connection.execute("pragma journal_mode=wal")
            connection.executescript("""
                create table if not exists maintenance_population_observations(
                    bucket_start integer primary key,
                    samples integer not null check(samples>0),
                    player_sum integer not null check(player_sum>=0),
                    player_max integer not null check(player_max>=0),
                    map_sum integer not null check(map_sum>=0),
                    last_observed_at integer not null
                );
                create index if not exists maintenance_population_time_idx
                    on maintenance_population_observations(bucket_start desc);
            """)
        try:
            os.chmod(self.path, 0o600)
        except FileNotFoundError:
            pass
        return self

    def record(self, player_count, map_count=0, observed_at=None):
        policy = load_policy(self.policy_path)
        epoch = int(observed_at if observed_at is not None else datetime.datetime.now(datetime.timezone.utc).timestamp())
        players = _integer(player_count, "player count", 0, 100000)
        maps = _integer(map_count, "map count", 0, 10000)
        bucket = epoch - epoch % policy["bucketSeconds"]
        cutoff = epoch - policy["retentionDays"] * 86400
        with contextlib.closing(self._connect()) as connection, connection:
            connection.execute(
                """insert into maintenance_population_observations(
                       bucket_start,samples,player_sum,player_max,map_sum,last_observed_at
                   ) values(?,1,?,?,?,?)
                   on conflict(bucket_start) do update set
                       samples=samples+1,
                       player_sum=player_sum+excluded.player_sum,
                       player_max=max(player_max,excluded.player_max),
                       map_sum=map_sum+excluded.map_sum,
                       last_observed_at=max(last_observed_at,excluded.last_observed_at)""",
                (bucket, players, players, maps, epoch),
            )
            connection.execute("delete from maintenance_population_observations where bucket_start<?", (cutoff,))
        return {"ok": True, "bucketStart": _iso(bucket), "playerCount": players, "identitiesStored": False}

    def _rows(self, cutoff):
        with contextlib.closing(self._connect()) as connection:
            return [dict(row) for row in connection.execute(
                "select * from maintenance_population_observations where bucket_start>=? order by bucket_start",
                (int(cutoff),),
            )]

    @staticmethod
    def _candidate_windows(policy, now):
        zone = ZoneInfo(policy["timezone"])
        earliest = now + policy["minimumNoticeMinutes"] * 60
        local = datetime.datetime.fromtimestamp(earliest, zone)
        start_date = local.date()
        candidates = []
        for day_offset in range(policy["horizonDays"] + 1):
            day = start_date + datetime.timedelta(days=day_offset)
            minute = policy["eligibleStartMinute"]
            latest = policy["eligibleEndMinute"] - policy["durationMinutes"]
            while minute <= latest:
                start = datetime.datetime.combine(day, datetime.time(minute // 60, minute % 60), zone)
                epoch = start.timestamp()
                if epoch >= earliest:
                    candidates.append((epoch, start))
                minute += policy["slotMinutes"]
        return candidates

    @staticmethod
    def _day_samples(rows, policy, candidate_local):
        zone = ZoneInfo(policy["timezone"])
        start_minute = candidate_local.hour * 60 + candidate_local.minute
        end_minute = start_minute + policy["durationMinutes"]
        grouped = {}
        for row in rows:
            local = datetime.datetime.fromtimestamp(row["bucket_start"], zone)
            minute = local.hour * 60 + local.minute
            if start_minute <= minute < end_minute:
                grouped.setdefault(local.date(), []).append((local, row))
        expected = policy["durationMinutes"] * 60 // policy["bucketSeconds"]
        minimum = math.ceil(expected * policy["minimumWindowCoverage"])
        samples = []
        for day, entries in grouped.items():
            unique_buckets = {row["bucket_start"]: row for _, row in entries}
            if len(unique_buckets) < minimum:
                continue
            averages = [row["player_sum"] / row["samples"] for row in unique_buckets.values()]
            samples.append({
                "date": day,
                "weekday": day.weekday(),
                "mean": sum(averages) / len(averages),
                "peak": max(row["player_max"] for row in unique_buckets.values()),
                "occupied": any(row["player_max"] > 0 for row in unique_buckets.values()),
                "coverage": min(1.0, len(unique_buckets) / expected),
            })
        same_weekday = [sample for sample in samples if sample["weekday"] == candidate_local.weekday()]
        if len(same_weekday) >= policy["weekdayWeightingMinimumDays"]:
            return same_weekday, "same-weekday"
        return samples, "all-days"

    def _score(self, rows, policy, epoch, local):
        samples, scope = self._day_samples(rows, policy, local)
        means = [sample["mean"] for sample in samples]
        peaks = [sample["peak"] for sample in samples]
        occupied = sum(1 for sample in samples if sample["occupied"])
        mean_players = sum(means) / len(means) if means else 0.0
        p95_peak = _percentile(peaks, 0.95)
        occupied_probability = occupied / len(samples) if samples else 0.0
        player_minutes = mean_players * policy["durationMinutes"]
        risk = player_minutes + p95_peak * 2.0 + occupied_probability * 10.0
        measured = len(samples) >= policy["minimumSampleDays"]
        return {
            "startAt": _iso(epoch),
            "endAt": _iso(epoch + policy["durationMinutes"] * 60),
            "localStart": local.isoformat(),
            "localLabel": local.strftime("%a %Y-%m-%d %H:%M %Z"),
            "durationMinutes": policy["durationMinutes"],
            "expectedConcurrentPlayers": round(mean_players, 3),
            "expectedPlayerMinutes": round(player_minutes, 3),
            "p95PeakPlayers": round(p95_peak, 3),
            "occupiedProbability": round(occupied_probability, 4),
            "sampleDays": len(samples),
            "meanCoverage": round(sum(sample["coverage"] for sample in samples) / len(samples), 4) if samples else 0.0,
            "evidenceScope": scope,
            "riskScore": round(risk, 4),
            "measured": measured,
        }

    def status(self, now=None):
        policy = load_policy(self.policy_path)
        now = float(now if now is not None else datetime.datetime.now(datetime.timezone.utc).timestamp())
        rows = self._rows(now - policy["lookbackDays"] * 86400)
        scored = [self._score(rows, policy, epoch, local) for epoch, local in self._candidate_windows(policy, now)]
        measured = [row for row in scored if row["measured"]]
        measured.sort(key=lambda row: (row["riskScore"], row["startAt"]))
        zone = ZoneInfo(policy["timezone"])
        fallback = next((row for row in scored if datetime.datetime.fromisoformat(row["localStart"]).hour * 60 + datetime.datetime.fromisoformat(row["localStart"]).minute == policy["defaultMinute"]), scored[0] if scored else None)
        recommendations = measured[:policy["recommendationCount"]] if measured else ([fallback] if fallback else [])
        baseline = fallback
        best = recommendations[0] if recommendations else None
        saved = None
        reduction = None
        if best and baseline and measured:
            saved = max(0.0, baseline["expectedPlayerMinutes"] - best["expectedPlayerMinutes"])
            reduction = 0.0 if baseline["expectedPlayerMinutes"] <= 0 else saved / baseline["expectedPlayerMinutes"]
        source = "measured-presence" if measured else "policy-fallback-learning"
        latest = rows[-1]["last_observed_at"] if rows else None
        first = rows[0]["bucket_start"] if rows else None
        return {
            "ok": bool(best),
            "schemaVersion": SCHEMA_VERSION,
            "state": "ready" if best else "no-candidate",
            "source": source,
            "confidence": "high" if measured and best["sampleDays"] >= 4 else "moderate" if measured else "low-learning",
            "generatedAt": _iso(now),
            "timezone": str(zone),
            "policy": {key: value for key, value in policy.items() if not key.endswith("Minute")},
            "evidence": {
                "observationBuckets": len(rows),
                "firstObservationAt": _iso(first) if first is not None else None,
                "lastObservationAt": _iso(latest) if latest is not None else None,
                "identitiesStored": False,
                "coordinatesStored": False,
                "minimumSampleDays": policy["minimumSampleDays"],
            },
            "recommendation": best,
            "recommendations": recommendations,
            "baseline": baseline,
            "comparison": {
                "expectedPlayerMinutesSaved": round(saved, 3) if saved is not None else None,
                "expectedImpactReduction": round(reduction, 4) if reduction is not None else None,
            },
        }

    def prometheus(self, now=None):
        try:
            status = self.status(now=now)
            recommendation = status.get("recommendation") or {}
            baseline = status.get("baseline") or {}
            comparison = status.get("comparison") or {}
            return "".join([
                "dash_maintenance_planner_collector_up 1\n",
                f"dash_maintenance_planner_measured {int(status.get('source') == 'measured-presence')}\n",
                f"dash_maintenance_planner_observation_buckets {int((status.get('evidence') or {}).get('observationBuckets') or 0)}\n",
                f"dash_maintenance_planner_recommended_expected_players {float(recommendation.get('expectedConcurrentPlayers') or 0)}\n",
                f"dash_maintenance_planner_baseline_expected_players {float(baseline.get('expectedConcurrentPlayers') or 0)}\n",
                f"dash_maintenance_planner_expected_player_minutes_saved {float(comparison.get('expectedPlayerMinutesSaved') or 0)}\n",
            ])
        except Exception:
            return "dash_maintenance_planner_collector_up 0\n"

