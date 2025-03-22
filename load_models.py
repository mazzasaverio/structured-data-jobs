# Import the Base class and all models from your models.py
from src.db.models.models import Base, CompanyUrl, FrontierUrl, JobPost
from atlas_provider_sqlalchemy.ddl import print_ddl

# Generate DDL for PostgreSQL (based on your current configuration)
print_ddl("postgresql", [Base]) 