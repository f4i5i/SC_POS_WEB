"""
Database Utilities
Helper functions for database operations
"""

from app.models import db
import logging

logger = logging.getLogger(__name__)


def init_database():
    """Initialize database with tables"""
    try:
        db.create_all()
        logger.info("Database tables created successfully")
        return True
    except Exception as e:
        logger.error(f"Error creating database tables: {e}")
        return False


def reset_database():
    """
    Reset database (drop all tables and recreate)
    WARNING: This deletes all data!
    """
    try:
        db.drop_all()
        db.create_all()
        logger.info("Database reset successfully")
        return True
    except Exception as e:
        logger.error(f"Error resetting database: {e}")
        return False


def get_or_create(model, **kwargs):
    """
    Get existing record or create new one

    Args:
        model: SQLAlchemy model class
        **kwargs: Fields to search/create with

    Returns:
        tuple: (instance, created) where created is bool
    """
    instance = model.query.filter_by(**kwargs).first()
    if instance:
        return instance, False
    else:
        instance = model(**kwargs)
        db.session.add(instance)
        db.session.commit()
        return instance, True


def bulk_insert(model, data_list):
    """
    Bulk insert records

    Args:
        model: SQLAlchemy model class
        data_list: List of dictionaries with data

    Returns:
        int: Number of records inserted
    """
    try:
        objects = [model(**data) for data in data_list]
        db.session.bulk_save_objects(objects)
        db.session.commit()
        return len(objects)
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in bulk insert: {e}")
        return 0


def safe_commit():
    """
    Safely commit transaction with error handling

    Returns:
        bool: Success status
    """
    try:
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error committing transaction: {e}")
        return False


def paginate_query(query, page=1, per_page=50):
    """
    Paginate a query

    Args:
        query: SQLAlchemy query
        page: Page number (1-indexed)
        per_page: Items per page

    Returns:
        Pagination object
    """
    return query.paginate(page=page, per_page=per_page, error_out=False)


def execute_raw_sql(sql, params=None):
    """
    Execute raw SQL query

    Args:
        sql: SQL query string
        params: Query parameters (optional)

    Returns:
        Query result
    """
    try:
        if params:
            result = db.session.execute(sql, params)
        else:
            result = db.session.execute(sql)
        db.session.commit()
        return result
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error executing SQL: {e}")
        return None
