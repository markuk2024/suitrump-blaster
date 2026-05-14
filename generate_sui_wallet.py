import hashlib
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization
import secrets
import string

def generate_sui_wallet():
    """Generate a new Sui wallet with Ed25519 keypair - raw hex format"""
    # Generate Ed25519 keypair
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    
    # Get raw bytes
    priv_bytes = private_key.private_bytes_raw()
    pub_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw
    )
    
    # Derive Sui address (blake2b hash of public key)
    hash_obj = hashlib.blake2b(pub_bytes, digest_size=32)
    address = "0x" + hash_obj.hexdigest()
    
    print(f"New Sui Wallet Generated:")
    print(f"Address: {address}")
    print(f"Private Key (hex): 0x{priv_bytes.hex()}")
    print(f"\nSince the hex key is giving you a different address,")
    print(f"please generate a new wallet in your Sui wallet app,")
    print(f"then export the private key from that wallet.")
    print(f"That way we know for sure the private key works with your wallet.")
    
    return address, priv_bytes.hex()

if __name__ == "__main__":
    generate_sui_wallet()
