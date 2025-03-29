# Structured Data Jobs

This project aims to build a data pipeline that can collect data about companies and job opportunities, tailored to the information you care about and the types of roles you want to track. The pipeline will pull data directly from company websites and use OpenAI tools to structure it and populate the data model.

While the initial setup will focus on tech roles—particularly data engineering and software engineering—it’s designed to be easily adaptable for tracking any kind of role or information you’d like to analyze over time.

## Data Pipeline

### 0. Companies

Once installation and setup are complete, the first step is to prepare a seed list of companies we want to gather information on, including company details and job postings. We'll use each company's main domain as the primary key for identification. TODO: In the future, we could add a crawling and data collection layer to keep the company list up to date.

```bash
uv run -m src.pipeline.00_companies
```

### 1. Career Pages



```bash
uv run -m src.pipeline.01_career_pages
```

## Crawling Methodology

We're trying to identify all the pages where job listings are typically posted. To do this, we use the following approach. The crawler operates across different depth levels:

1.1 **Depth Level 0: Career Page Discovery**: We check for common URL patterns like /careers, /jobs, etc.
We'll implement several strategies, but to begin with, let's keep it simple. Most companies have a dedicated path for job postings, so we can take advantage of that. This method is fast, non-intrusive, and doesn't require interacting with the page.

1.2 **Depth Level ≥ 1**: Once we find a career-related page, the system follows it, since job listings are often nested deeper in the site or split into subpages. We then use OpenAI's LLM to analyze the structured output and decide whether a URL is a seed (to explore further) or a target (that lists all job postings directly). Also in this case, let's keep it simple for now

The crawler maintains state awareness, verifying target URL validity and handling broken links automatically.

### 2. Job Listings

The next step is to set up an independent crawler that regularly scans each target, uses Playwright to extract all the text (including expanding any job listings if needed), and then applies an LLM to extract each job listing. We'll store the relevant details in a new table.

The next step is to choose the role (for example Data Engineer and Software Engineer) from the role in job_posts table and extrat from the related url structured information following similat approach already adopted

### 3. Job Details

The next step is to configure a YAML file with a list of roles (like Data Engineer or Software Engineer), then use it to filter roles from the job_posts table and extract structured data from the related URLs, just like we did before. Go ahead and create the table, config files, and the necessary code to make this work.


### System Requirements

- Python 3.11+
- Docker + Docker Compose
- Neon Postgres database

### Installation Steps

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/lean-jobs-crawler.git
   cd lean-jobs-crawler
   ```

2. UV-based setup:
   ```bash
   # Install UV package manager
   curl -LsSf https://astral.sh/uv/install.sh | sh
   
   # Project initialization
   uv init
   
   # Dependency installation
   uv sync
   ```

3. Environment configuration:
   ```bash
   cp .env.example .env
   # Configure database and system settings
   ```

### Database Management

Using Alembic for schema migrations:

1. Initial setup:
   ```bash
   # Database initialization
   uv run alembic upgrade head
   ```

2. Schema modifications:
   ```bash
   # Generate migration
   uv run alembic revision --autogenerate -m "Description of changes"
   
   # Apply changes
   uv run alembic upgrade head
   ```

3. Migration management:
   ```bash
   # History viewing
   uv run alembic history
   
   # Version control
   uv run alembic downgrade <revision_id>
   uv run alembic downgrade -1
   ```

Important: Always review auto-generated migrations before deployment.

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


## Project Status

⚠️ **Early Development Phase** ⚠️

This project is in active early development. Core functionality is being implemented and architecture may evolve significantly. The codebase is under construction with ongoing major development.

Current Focus Areas:
- Database schema implementation
- Job posting crawler development
- Standardized content extraction system

Future planned enhancements include automated company discovery and advanced data analytics capabilities.

Contributors welcome - note that significant refactoring may occur as the project matures.