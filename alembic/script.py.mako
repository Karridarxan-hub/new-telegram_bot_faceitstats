"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    """
    Apply migration changes to upgrade the database schema.
    
    This function contains the forward migration operations that will be
    applied when upgrading the database to this revision.
    """
${upgrades if upgrades else "    pass"}


def downgrade() -> None:
    """
    Revert migration changes to downgrade the database schema.
    
    This function contains the reverse migration operations that will be
    applied when downgrading the database from this revision.
    
    WARNING: Downgrade operations may result in data loss. Ensure you have
    proper backups before running downgrade operations in production.
    """
${downgrades if downgrades else "    pass"}