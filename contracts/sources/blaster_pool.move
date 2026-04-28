module blaster::pool {
    use sui::transfer;
    use sui::tx_context::TxContext;
    use sui::object::UID;
    use std::vector;

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
        transfer::share_object(pool);
    }

    /// Join a pool
    public entry fun join_pool(
        pool: &mut Pool,
        player: address
    ) {
        assert!(pool.is_active, 0);
        
        if (!vector::contains(&pool.players, &player)) {
            vector::push_back(&mut pool.players, player);
        }
    }

    /// Mark pool as completed
    public entry fun close_pool(pool: &mut Pool) {
        pool.is_active = false;
    }

    /// Get pool information
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

    /// Get balance
    public fun get_balance(pool: &Pool): u64 {
        pool.balance
    }

    /// Get players in pool
    public fun get_players(pool: &Pool): vector<address> {
        pool.players
    }
}
