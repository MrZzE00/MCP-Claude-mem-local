# Contributing to MCP-Claude-mem-local

First off, thank you for considering contributing to MCP-Claude-mem-local! 🎉

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Making Changes](#making-changes)
- [Pull Request Process](#pull-request-process)
- [Style Guidelines](#style-guidelines)
- [Testing](#testing)
- [Documentation](#documentation)

---

## Code of Conduct

This project and everyone participating in it is governed by our commitment to creating a welcoming and inclusive environment. Please be respectful and constructive in all interactions.

---

## Getting Started

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- Ollama
- Git

### Fork and Clone

1. Fork the repository on GitHub
2. Clone your fork locally:
   ```bash
   git clone https://github.com/YOUR_USERNAME/synaptic.git
   cd synaptic
   ```
3. Add the upstream remote:
   ```bash
   git remote add upstream https://github.com/original-org/synaptic.git
   ```

---

## Development Setup

### 1. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 3. Start Services

```bash
# Start PostgreSQL
docker-compose up -d postgres

# Pull embedding model
ollama pull nomic-embed-text
```

### 4. Initialize Database

```bash
docker exec synaptic-postgres psql -U synaptic -d synaptic -f docker/init.sql
```

### 5. Run Tests

```bash
pytest tests/ -v
```

---

## Making Changes

### Branch Naming

Use descriptive branch names:

- `feature/add-team-sync` — New features
- `fix/embedding-format` — Bug fixes
- `docs/api-reference` — Documentation
- `refactor/storage-layer` — Code refactoring
- `test/memory-stats` — Test additions

### Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation
- `style`: Formatting (no code change)
- `refactor`: Code restructuring
- `test`: Adding tests
- `chore`: Maintenance

Examples:
```
feat(server): add batch memory insertion

fix(embeddings): handle empty text input

docs(readme): add team setup instructions
```

---

## Pull Request Process

### Before Submitting

1. **Update from upstream:**
   ```bash
   git fetch upstream
   git rebase upstream/main
   ```

2. **Run all checks:**
   ```bash
   # Format code
   black src/ tests/
   
   # Lint
   ruff check src/ tests/
   
   # Type check
   mypy src/
   
   # Tests
   pytest tests/ -v --cov=src
   ```

3. **Update documentation** if needed

### Submitting

1. Push your branch:
   ```bash
   git push origin feature/your-feature
   ```

2. Open a Pull Request on GitHub

3. Fill out the PR template:
   - Description of changes
   - Related issues
   - Testing done
   - Screenshots (if UI changes)

### Review Process

- At least one maintainer review required
- All CI checks must pass
- Address review feedback promptly
- Squash commits if requested

---

## Style Guidelines

### Python

We use [Black](https://black.readthedocs.io/) for formatting and [Ruff](https://docs.astral.sh/ruff/) for linting.

```bash
# Format
black src/ tests/

# Lint
ruff check src/ tests/

# Fix auto-fixable issues
ruff check --fix src/ tests/
```

Configuration is in `pyproject.toml`.

### Key Style Points

- Line length: 100 characters
- Use type hints for function signatures
- Docstrings for public functions (Google style)
- Async/await for I/O operations

### Example

```python
async def store_memory(
    content: str,
    category: str,
    summary: str | None = None,
    tags: list[str] | None = None,
    importance: float = 0.5,
) -> str:
    """
    Store a new memory with embedding.

    Args:
        content: Full text content of the memory
        category: Category (bugfix, decision, feature, etc.)
        summary: Optional short summary
        tags: Optional list of tags
        importance: Importance score between 0.0 and 1.0

    Returns:
        UUID of the created memory

    Raises:
        ConnectionError: If database is unavailable
        ValueError: If category is invalid
    """
    ...
```

---

## Testing

### Running Tests

```bash
# All tests
pytest tests/ -v

# With coverage
pytest tests/ --cov=src --cov-report=html

# Specific test file
pytest tests/test_server.py -v

# Specific test
pytest tests/test_server.py::test_store_memory -v
```

### Writing Tests

- Place tests in `tests/` directory
- Mirror source structure: `src/server.py` → `tests/test_server.py`
- Use pytest fixtures for common setup
- Test both success and error cases

Example:

```python
import pytest
from src.server import store_memory, retrieve_memories

@pytest.fixture
async def db_pool():
    """Create test database connection."""
    # Setup
    pool = await create_test_pool()
    yield pool
    # Teardown
    await pool.close()

@pytest.mark.asyncio
async def test_store_memory_success(db_pool):
    """Test storing a memory successfully."""
    result = await store_memory(
        content="Test content",
        category="discovery",
        summary="Test summary"
    )
    assert "Memory stored with ID:" in result

@pytest.mark.asyncio
async def test_store_memory_invalid_category(db_pool):
    """Test storing with invalid category raises error."""
    result = await store_memory(
        content="Test content",
        category="invalid_category"
    )
    assert "Error" in result
```

---

## Documentation

### Updating Docs

Documentation is in `docs/` directory using Markdown.

```bash
# Serve docs locally
mkdocs serve

# Build docs
mkdocs build
```

### Documentation Structure

```
docs/
├── index.md              # Home page
├── getting-started.md    # Installation guide
├── architecture.md       # System design
├── api-reference.md      # MCP tools API
├── configuration.md      # Config options
├── team-setup.md         # Multi-user setup
├── migration.md          # Migration guides
└── troubleshooting.md    # Common issues
```

### Adding New Docs

1. Create the Markdown file in `docs/`
2. Add to `mkdocs.yml` navigation
3. Link from relevant existing docs

---

## Questions?

- Open an issue for bugs or feature requests
- Start a discussion for questions
- Tag maintainers for urgent issues

Thank you for contributing! 🧠✨