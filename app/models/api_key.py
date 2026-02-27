from datetime import datetime
from enum import Enum
import hashlib
from app import db


class APIKeyRole(Enum):
    """Enum for API key roles."""
    MERCHANT = "MERCHANT"
    BANK = "BANK"
    ADMIN = "ADMIN"
    INTERNAL_AGENT = "INTERNAL_AGENT"


class APIKey(db.Model):
    """API Key model for client authentication."""
    
    __tablename__ = 'api_keys'
    
    id = db.Column(db.Integer, primary_key=True)
    client_name = db.Column(db.String(255), nullable=False, index=True)
    key_hash = db.Column(db.String(255), unique=True, nullable=False, index=True)
    role = db.Column(db.Enum(APIKeyRole), nullable=False)
    allowed_ips = db.Column(db.JSON, nullable=True)  # List of allowed IP addresses
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    revoked_at = db.Column(db.DateTime, nullable=True, index=True)
    
    def __repr__(self):
        return f'<APIKey {self.client_name}>'
    
    @staticmethod
    def generate_key_hash(api_key):
        """Generate hash of API key for secure storage."""
        return hashlib.sha256(api_key.encode()).hexdigest()
    
    @classmethod
    def create_key(cls, client_name, api_key, role, allowed_ips=None):
        """
        Create a new API key.
        
        Args:
            client_name: Name of the client
            api_key: The actual API key (will be hashed)
            role: APIKeyRole enum value
            allowed_ips: Optional list of allowed IPs
        
        Returns:
            APIKey instance
        """
        key_hash = cls.generate_key_hash(api_key)
        return cls(
            client_name=client_name,
            key_hash=key_hash,
            role=role,
            allowed_ips=allowed_ips or []
        )
    
    def is_active(self):
        """Check if API key is active (not revoked)."""
        return self.revoked_at is None
    
    def revoke(self):
        """Revoke this API key."""
        self.revoked_at = datetime.utcnow()
    
    def to_dict(self, include_hash=False):
        """Convert to dictionary representation."""
        data = {
            'id': self.id,
            'client_name': self.client_name,
            'role': self.role.value,
            'allowed_ips': self.allowed_ips,
            'created_at': self.created_at.isoformat(),
            'revoked_at': self.revoked_at.isoformat() if self.revoked_at else None,
            'is_active': self.is_active(),
        }
        if include_hash:
            data['key_hash'] = self.key_hash
        return data
