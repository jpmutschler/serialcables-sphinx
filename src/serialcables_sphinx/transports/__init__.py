"""
Transport layer implementations for Sphinx.

Defines the interface that HYDRA and other transports implement.
"""

from serialcables_sphinx.transports.base import MCTPTransport

__all__ = ["MCTPTransport"]
