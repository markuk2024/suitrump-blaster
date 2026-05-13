#[allow(duplicate_alias)]
module blaster::pool {
    use sui::transfer;
    use sui::tx_context::{TxContext, tx_context};
    use sui::object;
    use sui::coin::{Self, Coin};
    use sui::balance::{Self, Balance};
    use sui::sui::SUI;
    use sui::dynamic_field;
    use std::vector;

    /// Error codes
    const EPoolNotActive: u64 = 0;
    const ENoFunds: u64 = 1;
    const EInvalidFee: u64 = 2;

    /// Dynamic field key for storing SUI balance
    public struct EscrowKey has copy, drop, store {}

    /// SUITRUMP token type
    const SUITRUMP_PACKAGE: address = @0xdeb831e796f16f8257681c0d5d4108fa94333060300b2459133a96631bf470b8;
    
    /// Cetus CLMM package for swapping
    const CETUS_PACKAGE: address = @0x1eabed72c53feb3805120a081dc15963c204dc8d091542592abaf7a35689b2fb;

    /// Pool structure that holds pool metadata
    public struct Pool has key {
        id: UID,
        name: vector<u8>,
        entry_fee: u64,
        balance: u64,
        dev_fee_percentage: u8,
        dev_wallet: address,
        players: vector<address>,
        is_active: bool,
    }

    /// Create a new competition pool
    public entry fun create_pool(
        name: vector<u8>,
        entry_fee: u64,
        dev_fee_percentage: u8,
        dev_wallet: address,
        ctx: &mut TxContext
    ) {
        assert!(dev_fee_percentage <= 100, EInvalidFee);
        
        let mut pool = Pool {
            id: object::new(ctx),
            name,
            entry_fee,
            balance: 0,
            dev_fee_percentage,
            dev_wallet,
            players: vector::empty(),
            is_active: true,
        };
        
        // Initialize escrow balance as dynamic field (starts at 0)
        dynamic_field::add(&mut pool.id, EscrowKey {}, balance::zero<SUI>());
        
        transfer::share_object(pool);
    }

    /// Original join_pool - adds player to list (kept for upgrade compatibility)
    public entry fun join_pool(
        pool: &mut Pool,
        player: address
    ) {
        assert!(pool.is_active, EPoolNotActive);
        
        if (!vector::contains(&pool.players, &player)) {
            vector::push_back(&mut pool.players, player);
        }
    }

    /// NEW: Deposit SUI into pool escrow (call this before join_pool in same tx)
    public entry fun deposit(
        pool: &mut Pool,
        payment: Coin<SUI>,
        _ctx: &mut TxContext
    ) {
        assert!(pool.is_active, EPoolNotActive);
        
        // Ensure escrow dynamic field exists (backward compat for old pools)
        if (!dynamic_field::exists_with_type<EscrowKey, Balance<SUI>>(&pool.id, EscrowKey {})) {
            dynamic_field::add(&mut pool.id, EscrowKey {}, balance::zero<SUI>());
        };
        
        let escrow: &mut Balance<SUI> = dynamic_field::borrow_mut(&mut pool.id, EscrowKey {});
        let payment_balance = coin::into_balance(payment);
        let payment_value = balance::value(&payment_balance);
        balance::join(escrow, payment_balance);
        
        // Update legacy balance field for compatibility
        pool.balance = pool.balance + payment_value;
    }

    /// NEW: Deposit + Join in one call (convenience function)
    public entry fun deposit_and_join(
        pool: &mut Pool,
        payment: Coin<SUI>,
        player: address,
        ctx: &mut TxContext
    ) {
        deposit(pool, payment, ctx);
        join_pool(pool, player);
    }

    /// NEW: Distribute rewards from escrow to winners
    /// winners and amounts are parallel vectors (both in MIST)
    /// NOTE: Currently distributes SUI. To distribute SUITRUMP, use swap function
    public entry fun distribute_rewards(
        pool: &mut Pool,
        winners: vector<address>,
        amounts: vector<u64>,
        ctx: &mut TxContext
    ) {
        assert!(vector::length(&winners) > 0, ENoFunds);
        
        // Initialize escrow if missing (backward compat)
        if (!dynamic_field::exists_with_type<EscrowKey, Balance<SUI>>(&pool.id, EscrowKey {})) {
            dynamic_field::add(&mut pool.id, EscrowKey {}, balance::zero<SUI>());
        };
        
        let escrow: &mut Balance<SUI> = dynamic_field::borrow_mut(&mut pool.id, EscrowKey {});
        let total_available = balance::value(escrow);
        
        assert!(total_available > 0, ENoFunds);
        
        let num_winners = vector::length(&winners);
        let num_amounts = vector::length(&amounts);
        assert!(num_winners == num_amounts, EInvalidFee);
        
        let mut i = 0;
        while (i < num_winners) {
            let winner = *vector::borrow(&winners, i);
            let amount = *vector::borrow(&amounts, i);
            
            if (amount > 0 && amount <= total_available) {
                let payout = coin::take(escrow, amount, ctx);
                transfer::public_transfer(payout, winner);
            };
            
            i = i + 1;
        };
        
    }

    /// NEW: Distribute rewards with SUITRUMP swap via Cetus CLMM
    /// Swaps SUI to SUITRUMP before distributing to winners
    /// Dev fee is kept in SUI
    public entry fun distribute_rewards_suitrump(
        pool: &mut Pool,
        winners: vector<address>,
        amounts: vector<u64>,
        dev_fee_amount: u64,
        cetus_pool_id: address,
        ctx: &mut TxContext
    ) {
        assert!(vector::length(&winners) > 0, ENoFunds);
        
        // Initialize escrow if missing (backward compat)
        if (!dynamic_field::exists_with_type<EscrowKey, Balance<SUI>>(&pool.id, EscrowKey {})) {
            dynamic_field::add(&mut pool.id, EscrowKey {}, balance::zero<SUI>());
        };
        
        let escrow: &mut Balance<SUI> = dynamic_field::borrow_mut(&mut pool.id, EscrowKey {});
        let total_available = balance::value(escrow);
        
        assert!(total_available > 0, ENoFunds);
        
        // Take dev fee in SUI
        if (dev_fee_amount > 0 && dev_fee_amount <= total_available) {
            let dev_payout = coin::take(escrow, dev_fee_amount, ctx);
            transfer::public_transfer(dev_payout, pool.dev_wallet);
        };
        
        let remaining = balance::value(escrow);
        
        // Swap remaining SUI to SUITRUMP via Cetus CLMM
        // Note: This requires the Cetus pool object and proper swap integration
        // For now, distribute SUI as fallback until Cetus integration is complete
        let num_winners = vector::length(&winners);
        let num_amounts = vector::length(&amounts);
        assert!(num_winners == num_amounts, EInvalidFee);
        
        let mut i = 0;
        while (i < num_winners) {
            let winner = *vector::borrow(&winners, i);
            let amount = *vector::borrow(&amounts, i);
            
            if (amount > 0 && amount <= remaining) {
                let payout = coin::take(escrow, amount, ctx);
                transfer::public_transfer(payout, winner);
            };
            
            i = i + 1;
        };
    }

    /// Mark pool as completed
    public entry fun close_pool(pool: &mut Pool) {
        pool.is_active = false;
    }

    /// Reopen a pool for the next cycle
    public entry fun reopen_pool(pool: &mut Pool) {
        pool.is_active = true;
    }

    /// Get pool information (unchanged signature for upgrade compat)
    public fun get_pool_info(pool: &Pool): (vector<u8>, u64, u64, u8, address, bool, u64) {
        (
            pool.name,
            pool.entry_fee,
            pool.balance,
            pool.dev_fee_percentage,
            pool.dev_wallet,
            pool.is_active,
            vector::length(&pool.players)
        )
    }

    /// Original get_balance (kept for upgrade compat)
    public fun get_balance(pool: &Pool): u64 {
        pool.balance
    }

    /// NEW: Get actual on-chain escrow balance in MIST
    public fun get_escrow_balance(pool: &Pool): u64 {
        if (dynamic_field::exists_with_type<EscrowKey, Balance<SUI>>(&pool.id, EscrowKey {})) {
            let escrow: &Balance<SUI> = dynamic_field::borrow(&pool.id, EscrowKey {});
            balance::value(escrow)
        } else {
            0
        }
    }

    /// Get players in pool
    public fun get_players(pool: &Pool): vector<address> {
        pool.players
    }

    /// NEW: Admin refund all escrow to dev wallet
    public entry fun refund_all(pool: &mut Pool, ctx: &mut TxContext) {
        if (dynamic_field::exists_with_type<EscrowKey, Balance<SUI>>(&pool.id, EscrowKey {})) {
            let escrow: &mut Balance<SUI> = dynamic_field::borrow_mut(&mut pool.id, EscrowKey {});
            let value = balance::value(escrow);
            if (value > 0) {
                let refund = coin::take(escrow, value, ctx);
                transfer::public_transfer(refund, pool.dev_wallet);
            };
        };
        pool.is_active = false;
    }

    /// NEW: Distribute rewards from external coins (not escrow)
    /// Used for distributing swapped tokens (e.g., SUITRUMP)
    /// Only callable by dev wallet
    /// Generic over any coin type
    public entry fun distribute_external_rewards<T>(
        pool: &mut Pool,
        coin: Coin<T>,
        winners: vector<address>,
        amounts: vector<u64>,
        ctx: &mut TxContext
    ) {
        assert!(tx_context::signer(ctx) == pool.dev_wallet, EInvalidFee);
        
        let num_winners = vector::length(&winners);
        let num_amounts = vector::length(&amounts);
        assert!(num_winners == num_amounts, EInvalidFee);
        
        let mut i = 0;
        while (i < num_winners) {
            let winner = *vector::borrow(&winners, i);
            let amount = *vector::borrow(&amounts, i);
            
            if (amount > 0) {
                let payout = coin::split(&mut coin, amount, ctx);
                transfer::public_transfer(payout, winner);
            };
            
            i = i + 1;
        };
        
        // Return remaining coins to dev wallet
        transfer::public_transfer(coin, pool.dev_wallet);
    }

    /// NEW: Withdraw SUI from escrow for external swapping
    /// Only callable by dev wallet
    public entry fun withdraw_from_escrow(pool: &mut Pool, amount: u64, ctx: &mut TxContext) {
        assert!(tx_context::signer(ctx) == pool.dev_wallet, EInvalidFee);
        
        if (!dynamic_field::exists_with_type<EscrowKey, Balance<SUI>>(&pool.id, EscrowKey {})) {
            dynamic_field::add(&mut pool.id, EscrowKey {}, balance::zero<SUI>());
        };
        
        let escrow: &mut Balance<SUI> = dynamic_field::borrow_mut(&mut pool.id, EscrowKey {});
        let available = balance::value(escrow);
        
        assert!(amount > 0 && amount <= available, ENoFunds);
        
        let withdrawal = coin::take(escrow, amount, ctx);
        transfer::public_transfer(withdrawal, pool.dev_wallet);
        
        // Update legacy balance field
        pool.balance = pool.balance - amount;
    }
}
