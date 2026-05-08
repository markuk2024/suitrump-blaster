module suitrump::token {
    use sui::coin::{Self, Coin, TreasuryCap};
    use sui::transfer;
    use sui::tx_context::TxContext;
    use sui::object::UID;
    use sui::dynamic_field;

    /// Error codes
    const ENotAuthorized: u64 = 0;
    const EInsufficientBalance: u64 = 1;

    /// SUITRUMP token type
    public struct SUITRUMP has drop {}

    /// Authority to mint/burn SUITRUMP tokens
    public struct MintAuthority has key {
        id: UID,
        admin: address,
        treasury_cap: TreasuryCap<SUITRUMP>,
    }

    /// Dynamic field key for tracking authorized swappers
    public struct SwapperKey has copy, drop, store {}

    /// Create the SUITRUMP token and mint authority
    public entry fun create_token(
        initial_supply: u64,
        admin: address,
        ctx: &mut TxContext
    ) {
        let treasury_cap = coin::create_minted_currency<SUITRUMP>(initial_supply, ctx);
        
        let mut authority = MintAuthority {
            id: object::new(ctx),
            admin,
            treasury_cap,
        };
        
        // Initialize swapper whitelist
        dynamic_field::add(&mut authority.id, SwapperKey {}, vector::empty<address>());
        
        transfer::share_object(authority);
    }

    /// Mint additional SUITRUMP tokens (admin only)
    public entry fun mint_tokens(
        authority: &mut MintAuthority,
        amount: u64,
        recipient: address,
        ctx: &mut TxContext
    ) {
        assert!(authority.admin == tx_context::sender(ctx), ENotAuthorized);
        
        let coins = coin::mint(&mut authority.treasury_cap, amount, ctx);
        transfer::public_transfer(coins, recipient);
    }

    /// Add an authorized swapper address
    public entry fun add_swapper(
        authority: &mut MintAuthority,
        swapper: address,
        ctx: &mut TxContext
    ) {
        assert!(authority.admin == tx_context::sender(ctx), ENotAuthorized);
        
        if (!dynamic_field::exists_with_type<SwapperKey, vector<address>>(&authority.id, SwapperKey {})) {
            dynamic_field::add(&mut authority.id, SwapperKey {}, vector::empty<address>());
        };
        
        let swappers: &mut vector<address> = dynamic_field::borrow_mut(&mut authority.id, SwapperKey {});
        if (!vector::contains(swappers, &swapper)) {
            vector::push_back(swappers, swapper);
        }
    }

    /// Remove an authorized swapper address
    public entry fun remove_swapper(
        authority: &mut MintAuthority,
        swapper: address,
        ctx: &mut TxContext
    ) {
        assert!(authority.admin == tx_context::sender(ctx), ENotAuthorized);
        
        if (dynamic_field::exists_with_type<SwapperKey, vector<address>>(&authority.id, SwapperKey {})) {
            let swappers: &mut vector<address> = dynamic_field::borrow_mut(&mut authority.id, SwapperKey {});
            let mut i = 0;
            let len = vector::length(swappers);
            while (i < len) {
                if (*vector::borrow(swappers, i) == swapper) {
                    vector::remove(swappers, i);
                    break
                };
                i = i + 1;
            }
        }
    }

    /// Check if an address is authorized to swap
    public fun is_authorized_swapper(authority: &MintAuthority, addr: address): bool {
        if (dynamic_field::exists_with_type<SwapperKey, vector<address>>(&authority.id, SwapperKey {})) {
            let swappers: &vector<address> = dynamic_field::borrow(&authority.id, SwapperKey {});
            vector::contains(swappers, &addr)
        } else {
            false
        }
    }

    /// Get the admin address
    public fun get_admin(authority: &MintAuthority): address {
        authority.admin
    }
}
