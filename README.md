# Lean Jobs Crawler

A specialized web crawler for discovering job postings directly from company websites, designed to work across different website structures using LLM-powered intelligence.

## Overview

This project aims to create a standardized approach to crawling job postings across various company websites, regardless of their structure or features. The crawler uses Large Language Models (LLMs) to:

1. Identify and store seed URLs (potential entry points that may lead to job postings)
2. Extract target URLs (where job posting information is actually located)
With all target URLs collected, you can seamlessly extract relevant information and conduct any desired analysis.

## Project Status

⚠️ **Early Development Phase** ⚠️

This project is currently in its very early stages of development. The core functionality is being implemented, and the architecture is subject to change. The repository has just been initialized, and significant parts of the codebase are still under construction.

Contributors are welcome, but be aware that major refactoring may occur as the project evolves.

## Architecture

The system follows a modular architecture:

- **URL Discovery**: Uses LLMs to identify promising seed URLs and target URLs
- **Crawling Engine**: Efficiently navigates websites while respecting robots.txt and rate limits
- **Content Extraction**: Parses job posting data into a standardized format
- **Storage Layer**: Persists both the raw and structured data in Neon Postgres
- **Orchestration**: Manages crawling jobs, retries, and scheduling

## Tech Stack

- **Package Management**: [uv](https://github.com/astral-sh/uv)
- **Database**: [Neon Postgres](https://neon.tech/)
- **ORM**: SQLAlchemy
- **Logging**: [Logfire](https://github.com/logfire-sh/logfire-python)
- **Runtime**: Python 3.11+
- **Containerization**: Docker for cloud deployment

## Getting Started

### Prerequisites

- Python 3.11+
- Docker and Docker Compose (for containerized deployment)
- Access to a Neon Postgres database

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/lean-jobs-crawler.git
   cd lean-jobs-crawler
   ```

2. Set up the project with uv:
   ```bash
   # Install uv if not installed
   curl -LsSf https://astral.sh/uv/install.sh | sh
   
   # Initialize the project
   uv init
   
   # Install dependencies from pyproject.toml
   uv sync
   ```

3. Configure environment variables:
   ```bash
   cp .env.example .env
   # Edit .env with your database credentials and other settings
   ```

### Local Development

```bash
# Run the crawler locally
uv run python -m src.main
```

### Docker Deployment

#### Using Docker

```bash
# Build the Docker image
docker build -t lean-jobs-crawler .

# Run the container
docker run -d --env-file .env lean-jobs-crawler
```

#### Using Docker Compose

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop all services
docker-compose down
```

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.



Requirements:
- The project should use uv as the package manager.
- It should support running, testing, and debugging both locally and in the cloud (possibly using Docker).
- Neon Postgres will be used to store the data.
- Logfire will be used for logging.
- Use SQLAlchemy come ORM

Show me the best practices for developing a high-performance, efficient, and effective specialized crawler starting from the abbove requirements


References:
