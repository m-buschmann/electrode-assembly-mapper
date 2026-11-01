"""Instance-aware routing for modular electrode assemblies.

Component definitions contain reusable local pin mappings. Assembly connections
join fully qualified instance pins, so identical local pin names on different
components remain distinct.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class ComponentDefinition:
    """Reusable pin mapping for one hardware model."""

    model_name: str
    component_type: str
    mapping: dict[Any, Any]

    @classmethod
    def from_json(cls, path: str | Path) -> "ComponentDefinition":
        with open(path, encoding="utf-8") as file:
            data = json.load(file)

        mapping = {
            _normalise_value(source): _normalise_value(destination)
            for source, destination in data["mapping"].items()
        }
        definition = cls(
            model_name=data.get("name", Path(path).stem),
            component_type=data.get("component_type", "component"),
            mapping=mapping,
        )
        definition.validate()
        return definition

    def validate(self) -> None:
        """Reject ambiguous local mappings before they enter an assembly."""
        destinations = list(self.mapping.values())
        if len(destinations) != len(set(_key(value) for value in destinations)):
            raise ValueError(
                f"Component model {self.model_name!r} maps multiple local pins "
                "to the same destination pin."
            )


def _normalise_value(value: Any) -> Any:
    text = str(value)
    return int(text) if text.isdigit() else value


def _key(value: Any) -> str:
    """Return the identity used for local pins in fully qualified names."""
    return str(value)


def make_fqn(instance_id: str, pin: Any) -> str:
    """Build a fully qualified pin name such as ``flex_left.pad_1``."""
    if not instance_id or "." in instance_id:
        raise ValueError("instance_id must be non-empty and must not contain '.'.")
    if pin is None or str(pin) == "":
        raise ValueError("pin must be non-empty.")
    return f"{instance_id}.{pin}"


def split_fqn(fqn: str) -> tuple[str, str]:
    """Split a fully qualified pin and reject malformed values."""
    instance_id, separator, pin = fqn.partition(".")
    if not separator or not instance_id or not pin or "." in instance_id:
        raise ValueError(f"Invalid fully qualified pin: {fqn!r}")
    return instance_id, pin


class AssemblyRouter:
    """Validate and traverse a one-to-one physical signal assembly."""

    def __init__(self) -> None:
        self.models: dict[str, ComponentDefinition] = {}
        self.instances: dict[str, str] = {}
        self.outgoing: dict[str, str] = {}
        self.incoming: dict[str, str] = {}

    def register_model(self, definition: ComponentDefinition) -> None:
        if definition.model_name in self.models:
            raise ValueError(f"Duplicate component model: {definition.model_name}")
        self.models[definition.model_name] = definition

    def register_model_json(self, path: str | Path) -> None:
        self.register_model(ComponentDefinition.from_json(path))

    def add_instance(self, instance_id: str, model_name: str) -> None:
        if instance_id in self.instances:
            raise ValueError(f"Duplicate component instance: {instance_id}")
        if model_name not in self.models:
            raise KeyError(f"Unknown component model: {model_name}")
        self.instances[instance_id] = model_name

        definition = self.models[model_name]
        for source, destination in definition.mapping.items():
            self.add_connection(
                make_fqn(instance_id, f"in_{source}"),
                make_fqn(instance_id, f"out_{destination}"),
            )

    def add_connection(self, source_fqn: str, destination_fqn: str) -> None:
        """Connect two physical pins, enforcing one-to-one connectivity."""
        source_instance, _ = split_fqn(source_fqn)
        destination_instance, _ = split_fqn(destination_fqn)
        if source_instance not in self.instances:
            raise KeyError(f"Unknown source instance: {source_instance}")
        if destination_instance not in self.instances:
            raise KeyError(f"Unknown destination instance: {destination_instance}")
        if source_fqn in self.outgoing:
            raise ValueError(f"Source pin already has a connection: {source_fqn}")
        if destination_fqn in self.incoming:
            raise ValueError(
                f"Destination pin already has a connection: {destination_fqn}"
            )
        self.outgoing[source_fqn] = destination_fqn
        self.incoming[destination_fqn] = source_fqn

    def load_assembly_csv(self, path: str | Path) -> None:
        with open(path, newline="", encoding="utf-8") as file:
            sample = file.read(4096)
            file.seek(0)

            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",;")
            except csv.Error as error:
                raise ValueError(
                    "Could not determine the assembly CSV delimiter; "
                    "expected ',' or ';'."
                ) from error

            reader = csv.DictReader(file, dialect=dialect)

            for row_number, row in enumerate(reader, start=2):
                required = {
                    "source_instance",
                    "source_pin",
                    "destination_instance",
                    "destination_pin",
                }
                missing = required.difference(row)
                if missing:
                    raise ValueError(
                        f"Assembly CSV is missing columns: {sorted(missing)}"
                    )

                try:
                    self.add_connection(
                        make_fqn(
                            row["source_instance"].strip(),
                            f"out_{row['source_pin'].strip()}",
                        ),
                        make_fqn(
                            row["destination_instance"].strip(),
                            f"in_{row['destination_pin'].strip()}",
                        ),
                    )
                except (KeyError, ValueError) as error:
                    raise ValueError(
                        f"Invalid assembly row {row_number}: {error}"
                    ) from error

    def trace_forward(self, start_fqn: str) -> list[str]:
        """Trace one signal forward until its first unconnected pin."""
        return self._trace(start_fqn, self.outgoing)

    def trace_backward(self, end_fqn: str) -> list[str]:
        """Trace one signal backward until its first unconnected pin."""
        return self._trace(end_fqn, self.incoming)

    @staticmethod
    def _trace(start_fqn: str, links: dict[str, str]) -> list[str]:
        split_fqn(start_fqn)
        path = [start_fqn]
        visited = {start_fqn}
        current = start_fqn
        while current in links:
            current = links[current]
            if current in visited:
                cycle = " -> ".join(path + [current])
                raise ValueError(f"Routing cycle detected: {cycle}")
            visited.add(current)
            path.append(current)
        return path

    def report(
        self,
        starts: Iterable[str],
        terminal_categories: Iterable[str] | None = None,
        instance_categories: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return forward paths with complete/incomplete status."""
        terminals = {
            str(category).lower()
            for category in (
                terminal_categories
                if terminal_categories is not None
                else ("headstage",)
            )
        }

        report = []
        for start in starts:
            path = self.trace_forward(start)
            destination_instance, _ = split_fqn(path[-1])

            if (
                instance_categories is not None
                and destination_instance in instance_categories
            ):
                category = instance_categories[destination_instance]
            else:
                model = self.models[self.instances[destination_instance]]
                category = model.component_type

            report.append(
                {
                    "source": start,
                    "destination": path[-1],
                    "status": (
                        "complete"
                        if str(category).lower() in terminals
                        else "incomplete"
                    ),
                    "path": path,
                }
            )

        return report

    def validate(self) -> None:
        """Check that all stored links remain one-to-one and non-cyclic."""
        if len(self.outgoing) != len(self.incoming):
            raise ValueError("Assembly link indexes are inconsistent.")
        for source in self.outgoing:
            self.trace_forward(source)
