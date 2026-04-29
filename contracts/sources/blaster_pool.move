module blaster::pool {
    use sui::transfer;
    use sui::tx_context::{Self, TxContext};
    use sui::object::{Self, UID};
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

    /// Pool structure that holds pool metadata
    /// NOTE: balance field is deprecated; actual SUI escrow stored in dynamic field
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
        
        let pool = Pool {
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

    /// Deposit SUI into the pool escrow and register player
    public entry fun join_pool(
        pool: &mut Pool,
        payment: Coin<SUI>,
        player: address,
        ctx: &mut TxContext
    ) {
        assert!(pool.is_active, EPoolNotActive);
        
        // Add player to list if not already present
        if (!vector::contains(&pool.players, &player)) {
            vector::push_back(&mut pool.players, player);
        }
        
        // Ensure escrow dynamic field exists (backward compat for old pools)
        if (!dynamic_field::exists_with_type<EscrowKey, Balance<SUI>>(&pool.id, EscrowKey {})) {
            dynamic_field::add(&mut pool.id, EscrowKey {}, balance::zero<SUI>());
        };
        
        // Deposit payment into escrow (dynamic field)
        let escrow: &mut Balance<SUI> = dynamic_field::borrow_mut(&mut pool.id, EscrowKey {});
        let payment_balance = coin::into_balance(payment);
        let payment_value = balance::value(&payment_balance);
        balance::join(escrow, payment_balance);
        
        // Also update deprecated balance field for compatibility
        pool.balance = pool.balance + payment_value;
    }

    /// Distribute rewards to winners
    /// winners and amounts are parallel vectors
    public entry fun distribute_rewards(
        pool: &mut Pool,
        winners: vector<address>,
        amounts: vector<u64>,
        ctx: &mut TxContext
    ) {
        assert!(!pool.is_active || vector::length(&winners) > 0, ENoFunds);
        
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
        
        let i = 0;
        while (i < num_winners) {
            let winner = *vector::borrow(&winners, i);
            let amount = *vector::borrow(&amounts, i);
            
            if (amount > 0 && amount <= total_available) {
                let payout = coin::take(escrow, amount, ctx);
                transfer::public_transfer(payout, winner);
            };
            
            i = i + 1;
        };
        
        pool.is_active = false;
    }

    /// Mark pool as completed
    public entry fun close_pool(pool: &mut Pool) {
        pool.is_active = false;
    }

    /// Get pool information (balance field is deprecated; use get_escrow_balance for real SUI)
    public fun get_pool_info(pool: &Pool): (vector<u8>, u64, u64, u8, address, bool, u64) {
        (
            pool.name,
            pool.entry_fee,
            pool.balance,  // Deprecated - kept for backward compat
            pool.dev_fee_percentage,
            pool.dev_wallet,
            pool.is_active,
            vector::length(&pool.players)
        )
    }

    /// Get actual escrow balance in MIST
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

    /// Admin function: return all escrow funds to dev wallet
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
}
