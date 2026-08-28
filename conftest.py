"""
Pytest configuration for memograph.
"""
import pytest
import tempfile
import shutil
import os

from memograph import MemoryShard, ShardDomain, MemoGraph, ContextRouter


@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def graph(temp_dir):
    return MemoGraph()


@pytest.fixture
def router():
    return ContextRouter()


@pytest.fixture
def live_shard():
    return MemoryShard.create(
        content={"intent": "deploy", "constraints": ["zero-downtime"]},
        owner="agent-001",
        scope="session:test",
        domain=ShardDomain.LIVE,
    )


@pytest.fixture
def project_shard():
    return MemoryShard.create(
        content={"decision": "use postgresql", "reason": "ACID compliance"},
        owner="agent-001",
        scope="project:payments",
        domain=ShardDomain.PROJECT,
    )


@pytest.fixture
def enterprise_shard():
    return MemoryShard.create(
        content={"policy": "encrypt all data at rest"},
        owner="ciso",
        scope="org:acme",
        domain=ShardDomain.ENTERPRISE,
    )


@pytest.fixture
def populated_graph(graph, live_shard, project_shard, enterprise_shard):
    graph.add_shard(live_shard)
    graph.add_shard(project_shard)
    graph.add_shard(enterprise_shard)
    return graph
