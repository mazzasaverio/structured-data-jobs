# Lean Jobs Crawler

A specialized web crawler for discovering job postings directly from company websites, designed to work across different website structures using openAI.

## Overview

This project aims to create a standardized approach to crawling job postings across various company websites, regardless of their structure or features. The crawler uses Large Language Models (LLMs) to:

The system discovers and processes four types of URLs:

1. CompanyUrl: The main website URLs for companies with their names
2. Frontier: History of already explored URLs that shouldn't be crawled again
3. TargetUrl: Pages containing listings of multiple job postings
4. JobPostingUrl: Individual job description pages

> **Note:** In the current implementation, company URLs are populated manually. Future development will include a separate crawler to automatically discover and validate company career sites. The present focus is on identifying and storing job postings from known companies.


- Let's begin at the most basic level. Look for a link like 'Careers' or 'Work With Us' since, in 95% of cases, it will be on the homepage of the official website. (As usual, we’ll handle exceptions at the end)

I'm using Playwright to find and extract career-related URLs from company websites. (However, we should consider exploring more efficient alternatives to minimize dependencies while maintaining performance.) The crawler will function as follows:

- Depth Level 0: It will scan websites for links with keywords like "Careers," "Work With Us," or similar phrases, identifying relevant URLs based on the link text.
- Depth Level ≥ 1: After finding a career-related page, it will navigate to it, extract all textual content, and save it as a .txt file for further analysis.


## Project Status

⚠️ **Early Development Phase** ⚠️

This project is currently in its very early stages of development. The core functionality is being implemented, and the architecture is subject to change. The repository has just been initialized, and significant parts of the codebase are still under construction.

Current priorities:
- Setting up the database schema
- Implementing the crawling logic for job postings from known company sites
- Developing the content extraction for standardized job data

Future enhancements will include automated company discovery and more comprehensive data analysis.

Contributors are welcome, but be aware that major refactoring may occur as the project evolves.

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

