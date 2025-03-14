I want to create a GitHub project for a crawler that specializes in finding new job postings directly from company websites.

The crawler should follow a standardized approach, regardless of the company's website structure or features. To achieve this, we'll use an LLM to identify and store seed URLs (potential entry points that may lead to target URLs) and target URLs (where job posting information is actually located).



Requirements:
- The project should use uv as the package manager.
- It should support running, testing, and debugging both locally and in the cloud (possibly using Docker).
- Neon Postgres will be used to store the data.
- Logfire will be used for logging.
- Use SQLAlchemy come ORM

Show me the best practices for developing a high-performance, efficient, and effective specialized crawler starting from the abbove requirements


References:
