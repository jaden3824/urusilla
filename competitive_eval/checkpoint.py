"""Atomic, hash-chained per-episode checkpoints for deterministic resume."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .canonical import (
    atomic_write_json,
    canonical_bytes,
    canonical_json,
    sha256_bytes,
    strict_json_file,
)
from .errors import IntegrityError, ManifestError
from .manifests import EpisodeManifest, RunManifest, episode_sequence_sha256


EVENT_FORMAT = "competitive-eval-checkpoint-event-v1"
GENESIS_SHA256 = "0" * 64


@dataclass(frozen=True)
class CheckpointEvent:
    value: Mapping[str, Any]

    @property
    def sequence(self) -> int:
        return int(self.value["sequence"])

    @property
    def event_type(self) -> str:
        return str(self.value["event_type"])

    @property
    def payload(self) -> Mapping[str, Any]:
        return self.value["payload"]

    @property
    def event_sha256(self) -> str:
        return str(self.value["event_sha256"])


class CheckpointStore:
    def __init__(
        self,
        root: Path,
        run_manifest: RunManifest,
        episodes: Sequence[EpisodeManifest],
    ):
        self.root = root
        self.run_manifest = run_manifest
        self.episodes = tuple(episodes)
        self._episode_ids = {episode.episode_id for episode in episodes}
        if len(self._episode_ids) != len(episodes):
            raise ManifestError("checkpoint store received duplicate episodes")
        self._initialize()

    def _initialize(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        run_path = self.root / "run_manifest.json"
        expected_run = self.run_manifest.to_json() + "\n"
        if run_path.exists():
            if run_path.read_text(encoding="utf-8") != expected_run:
                raise IntegrityError("resume run manifest differs from the frozen run")
        else:
            atomic_write_json(run_path, self.run_manifest.value)

        episodes_path = self.root / "episodes.jsonl"
        expected_episodes = "".join(episode.to_json() + "\n" for episode in self.episodes)
        if episodes_path.exists():
            if episodes_path.read_text(encoding="utf-8") != expected_episodes:
                raise IntegrityError("resume episode manifest differs from the frozen run")
        else:
            from .canonical import atomic_write

            atomic_write(episodes_path, expected_episodes.encode("utf-8"))
        if episode_sequence_sha256(self.episodes) != self.run_manifest.value["episode_sequence_sha256"]:
            raise IntegrityError("run/episode sequence digest mismatch")
        (self.root / "events").mkdir(exist_ok=True)

    def _event_dir(self, episode_id: str) -> Path:
        if episode_id not in self._episode_ids:
            raise ManifestError(f"unknown episode for checkpoint: {episode_id}")
        return self.root / "events" / episode_id

    def load(self, episode_id: str) -> tuple[CheckpointEvent, ...]:
        directory = self._event_dir(episode_id)
        if not directory.exists():
            return ()
        files = sorted(directory.glob("*.json"))
        expected_names = [f"{index:04d}.json" for index in range(len(files))]
        if [path.name for path in files] != expected_names:
            raise IntegrityError("checkpoint event sequence is missing, duplicated, or renamed")
        events: list[CheckpointEvent] = []
        previous = GENESIS_SHA256
        for index, path in enumerate(files):
            value = strict_json_file(path)
            if type(value) is not dict:
                raise IntegrityError("checkpoint event is not an object")
            expected_keys = {
                "format",
                "episode_id",
                "sequence",
                "event_type",
                "payload",
                "previous_event_sha256",
                "event_sha256",
            }
            if set(value) != expected_keys:
                raise IntegrityError("checkpoint event fields changed")
            if (
                value["format"] != EVENT_FORMAT
                or value["episode_id"] != episode_id
                or value["sequence"] != index
                or value["previous_event_sha256"] != previous
            ):
                raise IntegrityError("checkpoint event identity or chain changed")
            core = dict(value)
            supplied = core.pop("event_sha256")
            calculated = sha256_bytes(canonical_bytes(core))
            if supplied != calculated:
                raise IntegrityError("checkpoint event digest mismatch")
            previous = supplied
            events.append(CheckpointEvent(value))
        terminal_positions = [
            index for index, event in enumerate(events) if event.event_type == "episode_terminal"
        ]
        if terminal_positions and terminal_positions != [len(events) - 1]:
            raise IntegrityError("events exist after a terminal checkpoint")
        return tuple(events)

    def append(
        self, episode_id: str, event_type: str, payload: Mapping[str, Any]
    ) -> CheckpointEvent:
        if event_type not in {"turn_completed", "episode_terminal"}:
            raise ManifestError(f"unknown checkpoint event type: {event_type}")
        existing = self.load(episode_id)
        if existing and existing[-1].event_type == "episode_terminal":
            raise IntegrityError("cannot append after terminal event")
        sequence = len(existing)
        previous = existing[-1].event_sha256 if existing else GENESIS_SHA256
        core: dict[str, Any] = {
            "format": EVENT_FORMAT,
            "episode_id": episode_id,
            "sequence": sequence,
            "event_type": event_type,
            "payload": dict(payload),
            "previous_event_sha256": previous,
        }
        core["event_sha256"] = sha256_bytes(canonical_bytes(core))
        directory = self._event_dir(episode_id)
        directory.mkdir(parents=True, exist_ok=True)
        atomic_write_json(directory / f"{sequence:04d}.json", core)
        return CheckpointEvent(core)

    def completed_episode_ids(self) -> set[str]:
        result: set[str] = set()
        for episode_id in self._episode_ids:
            events = self.load(episode_id)
            if events and events[-1].event_type == "episode_terminal":
                result.add(episode_id)
        return result

    def event_chain_digest(self) -> str:
        entries: list[str] = []
        for episode_id in sorted(self._episode_ids):
            events = self.load(episode_id)
            for event in events:
                entries.append(f"{episode_id}|{event.sequence}|{event.event_sha256}")
        return sha256_bytes(canonical_bytes(entries))

