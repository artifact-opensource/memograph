# Contributing to Memograph

Thank you for your interest in contributing to Memograph!

## Development Setup

```bash
# Clone the repository
git clone https://github.com/yourorg/memograph.git
cd memograph

# Install in development mode
pip install -e ".[dev]"

# Run tests
pytest

# Format code
ruff format .
ruff check --fix .
```

## Project Structure

```
memograph/
├── core/           # Core data structures and algorithms
│   ├── shard.py    # MemoryShard primitives
│   ├── router.py  # Context routing
│   ├── memograph.py # Graph operations
│   └── events.py  # Audit logging
├── lifecycle/      # Memory lifecycle management
│   ├── pipeline.py # Promotion/demotion
│   └── evictor.py # TTL-based forgetting
├── engines/        # Retrieval adapters
│   ├── base.py     # Adapter interface
│   ├── semantic_adapter.py
│   └── ...
├── auth/          # Permissions and authorization
└── ...
```

## Code Style

- Follow PEP 8
- Use type hints throughout
- Docstrings for all public APIs
- Keep functions focused and small

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=memograph --cov-report=html

# Run specific test file
pytest tests/test_shard.py -v
```

## Pull Request Process

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Ensure all tests pass
6. Submit a pull request

## Reporting Issues

Please report issues on our GitHub repository with:
- Python version
- Memograph version
- Steps to reproduce
- Expected vs actual behavior

## Questions?

Open an issue on GitHub or reach out to the maintainers.
