"""SQL Server integration boundary. The existing schema/credentials are not available
in this environment, so NO schema is invented: implementations must be supplied once
the real schema is documented. Until then structured lookups return None and the
agent answers from approved guideline chunks only."""
from typing import Protocol, Optional
from ..config import settings

class StructuredStore(Protocol):
    def lookup_program(self, university_id: str, program_id: str) -> Optional[dict]: ...
    def lookup_university(self, university_id: str) -> Optional[dict]: ...

class UnconfiguredStructuredStore:
    """Dev fixture: intentionally empty — never fabricates program/admission records."""
    def lookup_program(self, university_id, program_id): return None
    def lookup_university(self, university_id): return None

class SqlServerStore:  # pragma: no cover - requires the real external DB
    def __init__(self, dsn: str):
        import pyodbc  # installed only where SQL Server access is provisioned
        self.conn = pyodbc.connect(dsn, readonly=True)
    def lookup_program(self, university_id, program_id):
        raise NotImplementedError("Map to the documented Randyll SQL Server schema before enabling.")
    def lookup_university(self, university_id):
        raise NotImplementedError("Map to the documented Randyll SQL Server schema before enabling.")

def get_structured_store() -> StructuredStore:
    return SqlServerStore(settings.sqlserver_dsn) if settings.sqlserver_dsn else UnconfiguredStructuredStore()
