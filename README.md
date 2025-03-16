# Lean Jobs Crawler

A specialized web crawler is designed to scrape job postings directly from company websites. It follows a standardized method, leveraging an LLM to pinpoint the URLs where job listings are hosted.

## Project Status

⚠️ **Early Development Phase** ⚠️

This project is currently in its very early stages of development. The core functionality is being implemented, and the architecture is subject to change. The repository has just been initialized, and significant parts of the codebase are still under construction.

Current priorities:
- Setting up the database schema
- Implementing the crawling logic for job postings from known company sites
- Developing the content extraction for standardized job data

Future enhancements will include automated company discovery and more comprehensive data analysis.

Contributors are welcome, but be aware that major refactoring may occur as the project evolves.

## Overview

The system relies on two main database tables:

1. **CompanyUrl**: Stores the main website URLs of companies
2. **Frontier**: Tracks explored URLs, starting from the company's root URL (the seed). This table includes key fields such as:
   - **Depth** (indicating the level where the URL was found)
   - **Target status** – Indicates whether the URL contains a **list** of job postings.

> **Note:** Currently, company URLs are added manually. In future updates, a dedicated crawler will be implemented to automatically discover all companies in a given city. For now, the primary goal is to identify and store job postings from known companies.

## Crawling Process

The crawler operates at different depth levels:

- **Depth Level 0**: It scans websites for links with keywords like "Careers," "Work With Us," or similar phrases, identifying relevant URLs based on the link text. In approximately 95% of cases, these links are found on the homepage of the official website.

- **Depth Level ≥ 1**: Once a career-related page is found, the system navigates to it since job postings may be deeper within the site or in different subsections. Then, we use OpenAI's LLM structured output analysis to determine whether the URL is a seed child URL worth exploring further or a target URL that directly lists all job postings.

## Architecture

The system follows a modular architecture:

- **URL Discovery**: Uses LLMs to identify promising target URLs and job posting URLs
- **Crawling Engine**: Efficiently navigates websites while respecting robots.txt and rate limits
- **Frontier Management**: Tracks explored URLs to avoid redundant crawling
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