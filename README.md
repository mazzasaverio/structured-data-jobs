# Lean Jobs Crawler

A specialized web crawler is built to extract job postings directly from company websites. It uses a standardized method and leverages an LLM to identify the exact URLs where job listings are found. The aim is to have the data to create a platform that continuously provides an up-to-date view of the best companies, workplaces, and projects to work on.

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

- **Depth Level 0**: The crawler uses a multi-stage approach to locate company career pages, organized in order of increasing complexity:

1. **Direct URL Probing**
   - Attempts common career page paths like `/careers`, `/jobs`, `/work-with-us`
   - Fast and non-intrusive, doesn't require page interaction
   - Validates found pages by checking for job-related terms

2. **Simple Text Matching**
   - Scans the homepage for obvious career links
   - Looks for text like "careers", "jobs", "work with us", "join our team"
   - Minimal page parsing required

3. **Sitemap Exploration**
   - Checks if the site has a sitemap.xml
   - Scans for URLs containing career-related terms
   - Effective for sites with well-structured sitemaps
   
- **Depth Level ≥ 1**: Once a career-related page is found, the system navigates to it since job postings may be deeper within the site or in different subsections. Then, we use OpenAI's LLM structured output analysis to determine whether the URL is a seed child URL worth exploring further or a target URL that directly lists all job postings.

The script always checks whether there's no target URL in the frontier_urls table or if the existing target URL is broken.

The next step is to set up an independent crawler that regularly scans each target, uses Playwright to extract all the text (including expanding any job listings if needed), and then applies an LLM—using a structured approach similar to what's in the codebase—to extract each job listing. We'll store the relevant details in a new table.

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

### Database Migrations with Alembic

This project uses Alembic for database schema migrations. After setting up your environment:

1. Initialize the database (if first time):
   ```bash
   # First, ensure your database connection is properly configured in .env
   uv run alembic upgrade head
   ```

2. When making schema changes:
   ```bash
   # Create a new migration after modifying models
   uv run alembic revision --autogenerate -m "Description of changes"
   
   # Apply the migration
   uv run alembic upgrade head
   ```

3. Managing migrations:
   ```bash
   # View migration history
   uv run alembic history
   
   # Downgrade to a specific version
   uv run alembic downgrade <revision_id>
   
   # Downgrade one version
   uv run alembic downgrade -1
   ```

Note: Always review auto-generated migrations before applying them to ensure they correctly capture your intended changes.

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