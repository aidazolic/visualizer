"""datasets module."""
from __future__ import annotations

from collections.abc import Mapping
import dataclasses
import json
from typing import Any

from absl import logging
from etils import epath
from ml_croissant._src.core.issues import Issues, ValidationError
from ml_croissant._src.rdf_graph import graph
from ml_croissant._src.operation_graph import (
    build_structure_graph,
    ComputationGraph,
)
from ml_croissant._src.operation_graph.operations import (
    GroupRecordSet,
    ReadField,
)
import networkx as nx


def _load_file(filepath: epath.PathLike) -> tuple[epath.Path, dict]:
    """Loads the file.

    Args:
        filepath: the path to the Croissant file.

    Returns:
        A tuple with the path to the file and the file content.
    """
    filepath = epath.Path(filepath).expanduser().resolve()
    if not filepath.exists():
        raise ValueError(f"File {filepath} does not exist.")
    with filepath.open() as filedescriptor:
        return filepath, json.load(filedescriptor)


@dataclasses.dataclass
class Validator:
    """Static analysis of the issues in the Croissant file."""

    file_or_file_path: epath.PathLike
    issues: Issues = dataclasses.field(default_factory=Issues)
    file: dict = dataclasses.field(init=False)
    operations: ComputationGraph | None = None

    def run_static_analysis(self):
        try:
            file_path, self.file = _load_file(self.file_or_file_path)
            rdf_graph, rdf_nx_graph = graph.load_rdf_graph(self.file)
            rdf_namespace_manager = rdf_graph.namespace_manager
            nodes = graph.check_rdf_graph(self.issues, rdf_nx_graph)

            entry_node, structure_graph = build_structure_graph(self.issues, nodes)
            # Feature toggling: do not check for MovieLens, because we need more
            # features.
            if entry_node.uid == "Movielens-25M":
                return
            self.operations = ComputationGraph.from_nodes(
                issues=self.issues,
                metadata=entry_node,
                graph=structure_graph,
                croissant_folder=file_path.parent,
                rdf_namespace_manager=rdf_namespace_manager,
            )
            self.operations.check_graph()
        except Exception as exception:
            if self.issues.errors:
                raise ValidationError(self.issues.report()) from exception
            raise exception
        if self.issues.errors:
            raise ValidationError(self.issues.report())
        elif self.issues.warnings:
            logging.warning(self.issues.report())


@dataclasses.dataclass
class Dataset:
    """Python representation of a Croissant dataset.

    Args:
        file: A JSON object or a path to a Croissant file (string or pathlib.Path).
    """

    file: epath.PathLike
    operations: ComputationGraph | None = None

    def __post_init__(self):
        """Runs the static analysis of `file`."""
        self.validator = Validator(self.file)
        self.validator.run_static_analysis()
        self.file = self.validator.file
        self.operations = self.validator.operations

    def records(self, record_set: str) -> Records:
        return Records(self, record_set)


@dataclasses.dataclass
class Records:
    """Iterable set of records.

    Args:
        dataset: The parent dataset.
        record_set: The name of the record set.
    """

    dataset: Dataset
    record_set: str

    def __iter__(self):
        """Executes all operations, runs dynamic analysis and yields examples.

        Warning: at the moment, this method yields examples from the first explored
        record_set.
        """
        results: Mapping[str, Any] = {}
        operations = self.dataset.operations.graph
        for operation in nx.topological_sort(operations):
            logging.info('Executing "%s"', operation)
            kwargs = operations.nodes[operation].get("kwargs", {})
            previous_results = [
                results[previous_operation]
                for previous_operation in operations.predecessors(operation)
                if previous_operation in results
                # Filter out results that yielded `None`.
                and results[previous_operation] is not None
            ]
            if isinstance(operation, GroupRecordSet):
                # Only keep the record set whose name is `self.record_set`.
                # Note: this is a short-term solution. The long-term solution is to
                # re-compute the sub-graph of operations that is sufficient to compute
                # `self.record_set`.
                if operation.node.name != self.record_set:
                    continue
                assert len(previous_results) == 1, (
                    f'"{operation}" should have one and only one predecessor. Got:'
                    f" {len(previous_results)}."
                )
                previous_result = previous_results[0]
                for _, line in previous_result.iterrows():
                    read_fields = []
                    for read_field in operations.successors(operation):
                        assert isinstance(read_field, ReadField)
                        logging.info('Executing "%s"', read_field)
                        read_fields.append(read_field(line, **kwargs))
                    logging.info('Executing "%s"', operation)
                    yield operation(*read_fields, **kwargs)
            else:
                if isinstance(operation, ReadField) and not previous_results:
                    continue
                results[operation] = operation(*previous_results, **kwargs)