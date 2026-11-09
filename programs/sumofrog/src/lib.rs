//! Sumo Frog ($SUMO): a toy, devnet-only, proof-of-work mineable SPL token.
//!
//! Miners grind `nonce` off-chain until
//!     sha256(challenge || miner_pubkey || nonce_le) [first 8 bytes, big-endian] <= target
//! then call `mine`. The program re-checks the hash, mints the block reward to the
//! miner, and rolls the challenge forward so every solution works exactly once.
//! Difficulty retargets Bitcoin-style every `retarget_interval` blocks, the reward
//! halves every `halving_interval` blocks, and minting stops at `max_supply`.
use anchor_lang::prelude::*;
use solana_sha256_hasher::hashv;
use anchor_spl::associated_token::AssociatedToken;
use anchor_spl::metadata::{
    create_metadata_accounts_v3, mpl_token_metadata::types::DataV2, CreateMetadataAccountsV3,
    Metadata,
};
use anchor_spl::token::{self, Mint, MintTo, Token, TokenAccount};

declare_id!("6h1PqXArg2Ap1CJdR1hXXWhqSrzkeboqi5cx1y44NvTW");

pub const CONFIG_SEED: &[u8] = b"config";
pub const MINT_SEED: &[u8] = b"mint";
pub const DECIMALS: u8 = 9;
/// Retargets never move difficulty by more than 4x in one step (same as Bitcoin).
pub const MAX_ADJUST: i64 = 4;
/// Longest allowed retarget window (retarget_interval * target_block_time, in seconds).
/// Capping it at i64::MAX / 4 means the retarget maths can never wrap or saturate, so it
/// always follows the plain rule. That is still ~73 billion years, far beyond any real setting.
pub const MAX_RETARGET_WINDOW: u128 = (i64::MAX / MAX_ADJUST) as u128;
/// The shortest halving interval `set_schedule` can ever set (2 Nov 2026, Ribbit's third review):
/// half the live yearly schedule (525,600 blocks). A fixed floor, so the "at most half" limit
/// can't be applied again and again (525,600 -> 262,800 -> 131,400 -> ... -> 41 in 14 steps).
/// A schedule already shorter than this (test chains) can only keep its interval.
pub const MIN_HALVING_INTERVAL: u64 = 262_800;

#[program]
pub mod sumofrog {
    use super::*;

    /// One-time setup. Only the program's upgrade authority can call it, so nobody
    /// can front-run the deploy and set their own rules.
    pub fn initialize(ctx: Context<Initialize>, params: InitParams) -> Result<()> {
        require!(params_ok(&params), SumoError::BadParams);
        let clock = Clock::get()?;
        let mint = ctx.accounts.mint.key();
        let cfg = &mut ctx.accounts.config;
        cfg.authority = ctx.accounts.authority.key();
        cfg.mint = mint;
        cfg.bump = ctx.bumps.config;
        cfg.mint_bump = ctx.bumps.mint;
        cfg.challenge = genesis_challenge(&mint, clock.slot, clock.unix_timestamp);
        cfg.target = params.initial_target;
        cfg.initial_reward = params.initial_reward;
        cfg.halving_interval = params.halving_interval;
        cfg.retarget_interval = params.retarget_interval;
        cfg.target_block_time = params.target_block_time;
        cfg.max_supply = params.max_supply;
        cfg.blocks_mined = 0;
        cfg.total_minted = 0;
        cfg.epoch_start_ts = clock.unix_timestamp;
        cfg.last_solve_ts = clock.unix_timestamp;
        cfg.last_miner = Pubkey::default();
        cfg.last_reward = 0;
        Ok(())
    }

    /// Attach Metaplex metadata (name, symbol, image link) to the mint.
    /// The config PDA signs as mint authority; the setup wallet becomes update authority.
    pub fn create_metadata(
        ctx: Context<CreateMetadata>,
        name: String,
        symbol: String,
        uri: String,
    ) -> Result<()> {
        let bump = [ctx.accounts.config.bump];
        let seeds: &[&[u8]] = &[CONFIG_SEED, &bump];
        create_metadata_accounts_v3(
            CpiContext::new_with_signer(
                ctx.accounts.token_metadata_program.to_account_info(),
                CreateMetadataAccountsV3 {
                    metadata: ctx.accounts.metadata.to_account_info(),
                    mint: ctx.accounts.mint.to_account_info(),
                    mint_authority: ctx.accounts.config.to_account_info(),
                    payer: ctx.accounts.authority.to_account_info(),
                    update_authority: ctx.accounts.authority.to_account_info(),
                    system_program: ctx.accounts.system_program.to_account_info(),
                    rent: ctx.accounts.rent.to_account_info(),
                },
                &[seeds],
            ),
            DataV2 {
                name,
                symbol,
                uri,
                seller_fee_basis_points: 0,
                creators: None,
                collection: None,
                uses: None,
            },
            true,
            true,
            None,
        )
    }

    /// Submit a proof-of-work solution and mint the reward to the signer's own wallet.
    /// `challenge` must be the current one (so a stale or replayed answer fails cleanly)
    /// and the signer's pubkey is part of the hash, so nobody can copy someone else's nonce.
    pub fn mine(ctx: Context<Mine>, challenge: [u8; 32], nonce: u64) -> Result<()> {
        let a = &mut *ctx.accounts;
        let earner = a.miner.key();
        mine_core(&mut a.config, &a.mint, &a.miner_ata, &a.token_program, earner, challenge, nonce)
    }

    /// Same as `mine`, but the reward goes to `payout` (any wallet's public address) instead
    /// of the signer. The signer only pays the fees (and, the first time, the payout wallet's
    /// SUMO token account). The hash binds `payout`, not the signer, so a copied answer still
    /// pays the wallet it was found for. Mining to yourself with `mine` hashes the same way.
    pub fn mine_to(ctx: Context<MineTo>, challenge: [u8; 32], nonce: u64) -> Result<()> {
        let a = &mut *ctx.accounts;
        let earner = a.payout.key();
        mine_core(&mut a.config, &a.mint, &a.payout_ata, &a.token_program, earner, challenge, nonce)
    }

    /// Change the reward schedule (added 1 Nov 2026 for the yearly halving). Only the program's
    /// upgrade authority can call it, which already has full power over the program; once the
    /// upgrade key is given up this instruction can never run again. A change can only make the
    /// schedule meaner, never kinder (2 Nov 2026 fix): no block, now or later, pays more than the
    /// current schedule would, and halving can't be delayed or switched off. See `schedule_ok`.
    /// The 21M cap (`max_supply`) can't be changed at all.
    pub fn set_schedule(ctx: Context<SetSchedule>, initial_reward: u64, halving_interval: u64) -> Result<()> {
        let cfg = &mut ctx.accounts.config;
        require!(
            schedule_ok(
                cfg.initial_reward,
                cfg.halving_interval,
                cfg.blocks_mined,
                cfg.max_supply,
                initial_reward,
                halving_interval
            ),
            SumoError::BadParams
        );
        emit!(ScheduleChanged {
            block: cfg.blocks_mined,
            old_reward: cfg.initial_reward,
            new_reward: initial_reward,
            old_halving_interval: cfg.halving_interval,
            new_halving_interval: halving_interval,
        });
        cfg.initial_reward = initial_reward;
        cfg.halving_interval = halving_interval;
        Ok(())
    }
}

/// Shared by `mine` and `mine_to`: check the work against `earner`, mint to `ata`
/// (whose owner Anchor has already checked is `earner`), then roll the challenge forward.
fn mine_core<'info>(
    config: &mut Account<'info, Config>,
    mint: &Account<'info, Mint>,
    ata: &Account<'info, TokenAccount>,
    token_program: &Program<'info, Token>,
    earner: Pubkey,
    challenge: [u8; 32],
    nonce: u64,
) -> Result<()> {
    require!(challenge == config.challenge, SumoError::StaleChallenge);
    let hash = pow_hash(&config.challenge, &earner, nonce);
    require!(work_value(&hash) <= config.target, SumoError::InsufficientWork);
    let reward = capped_reward(
        config.initial_reward,
        config.halving_interval,
        config.blocks_mined,
        config.max_supply,
        config.total_minted,
    );
    require!(reward > 0, SumoError::SupplyExhausted);

    let bump = [config.bump];
    let seeds: &[&[u8]] = &[CONFIG_SEED, &bump];
    token::mint_to(
        CpiContext::new_with_signer(
            token_program.to_account_info(),
            MintTo {
                mint: mint.to_account_info(),
                to: ata.to_account_info(),
                authority: config.to_account_info(),
            },
            &[seeds],
        ),
        reward,
    )?;

    let clock = Clock::get()?;
    let cfg = config;
    cfg.blocks_mined = cfg.blocks_mined.checked_add(1).ok_or(SumoError::MathOverflow)?;
    cfg.total_minted = cfg.total_minted.checked_add(reward).ok_or(SumoError::MathOverflow)?;
    cfg.last_solve_ts = clock.unix_timestamp;
    cfg.last_miner = earner;
    cfg.last_reward = reward;
    // Single-use: the next challenge depends on this solution.
    cfg.challenge = next_challenge(&hash, clock.slot, cfg.blocks_mined);

    if cfg.blocks_mined % cfg.retarget_interval == 0 {
        let old = cfg.target;
        let elapsed = clock.unix_timestamp.saturating_sub(cfg.epoch_start_ts);
        cfg.target = retarget(old, elapsed, cfg.retarget_interval, cfg.target_block_time);
        cfg.epoch_start_ts = clock.unix_timestamp;
        emit!(Retargeted {
            block: cfg.blocks_mined,
            elapsed,
            old_target: old,
            new_target: cfg.target,
        });
    }

    emit!(BlockMined {
        block: cfg.blocks_mined,
        miner: earner,
        nonce,
        reward,
        total_minted: cfg.total_minted,
        target: cfg.target,
        timestamp: clock.unix_timestamp,
    });
    Ok(())
}

/// sha256(challenge || miner_pubkey || nonce_le): the proof-of-work hash.
pub fn pow_hash(challenge: &[u8; 32], miner: &Pubkey, nonce: u64) -> [u8; 32] {
    hashv(&[challenge, miner.as_ref(), &nonce.to_le_bytes()]).to_bytes()
}

/// The challenge after a solved block: sha256(solution_hash || slot_le || blocks_mined_le),
/// where `blocks_mined` already counts the block just solved.
pub fn next_challenge(solution: &[u8; 32], slot: u64, blocks_mined: u64) -> [u8; 32] {
    hashv(&[solution, &slot.to_le_bytes(), &blocks_mined.to_le_bytes()]).to_bytes()
}

/// The first challenge: sha256("sumo frog genesis" || mint || slot_le || unix_ts_le).
pub fn genesis_challenge(mint: &Pubkey, slot: u64, unix_ts: i64) -> [u8; 32] {
    hashv(&[b"sumo frog genesis", mint.as_ref(), &slot.to_le_bytes(), &unix_ts.to_le_bytes()])
        .to_bytes()
}

/// First 8 bytes of the hash as a big-endian number. Lower = more work.
pub fn work_value(hash: &[u8; 32]) -> u64 {
    u64::from_be_bytes(hash[0..8].try_into().unwrap())
}

/// Setup rules: everything positive, the cap can pay at least one block, and the retarget
/// window fits MAX_RETARGET_WINDOW (so `retarget` never hits an integer limit).
pub fn params_ok(p: &InitParams) -> bool {
    p.initial_reward > 0
        && p.halving_interval > 0
        && p.retarget_interval > 0
        && p.target_block_time > 0
        && p.initial_target > 0
        && p.max_supply >= p.initial_reward
        && (p.retarget_interval as u128) * (p.target_block_time as u128) <= MAX_RETARGET_WINDOW
}

/// Rules for `set_schedule` (tightened 2 Nov 2026 after Ribbit's review: the old rule compared
/// with the year-one reward, so after a halving the key holder could set the old reward again
/// and push the halving point out, undoing or switching off halving):
/// - the new reward is positive and within the cap;
/// - the new halving interval is past the blocks already mined (the new schedule starts in its
///   era 0) and no longer than the current interval (halving can come sooner, never later);
/// - the new halving interval is at least half the current one (added 2 Nov 2026, Ribbit's
///   second review): a shorter interval keeps repeating and the schedule then locks, so a typo
///   such as 41 for 525,600 would end issuance within about a day, for good;
/// - and it is at least MIN_HALVING_INTERVAL, or the current interval if that is already
///   shorter (Ribbit's third review): a fixed floor, so repeated halvings of the interval can't
///   walk it down step by step;
/// - the block being mined now pays no more than it does under the current schedule.
/// Together these mean every future block pays <= what the current schedule pays: both
/// schedules are then in era 0 now (blocks_mined < new <= current interval), so the new reward
/// is <= the current one, and for any later block the shorter interval has halved at least as
/// many times. One side effect: once the first halving has happened (blocks_mined reaches the
/// current interval) no change passes any more, so the schedule is then fixed for good.
pub fn schedule_ok(
    cur_initial: u64,
    cur_halving: u64,
    blocks_mined: u64,
    max_supply: u64,
    new_initial: u64,
    new_halving: u64,
) -> bool {
    // Order matters: the interval checks run first, so block_reward never divides by zero.
    new_halving > blocks_mined
        && cur_halving > 0
        && new_halving <= cur_halving
        && (new_halving as u128) * 2 >= cur_halving as u128
        && new_halving >= cur_halving.min(MIN_HALVING_INTERVAL)
        && new_initial > 0
        && new_initial <= max_supply
        && block_reward(new_initial, new_halving, blocks_mined) <= block_reward(cur_initial, cur_halving, blocks_mined)
}

/// The reward `mine` pays: the halving schedule, cut down so the total never passes max_supply.
pub fn capped_reward(initial: u64, halving_interval: u64, blocks_mined: u64, max_supply: u64, total_minted: u64) -> u64 {
    block_reward(initial, halving_interval, blocks_mined).min(max_supply.saturating_sub(total_minted))
}

pub fn block_reward(initial: u64, halving_interval: u64, blocks_mined: u64) -> u64 {
    let era = blocks_mined / halving_interval;
    if era >= 64 {
        0
    } else {
        initial >> era
    }
}

/// new_target = old * actual / expected, with `actual` clamped to [expected/4, expected*4].
/// Faster than planned -> smaller target -> harder.
pub fn retarget(old: u64, elapsed: i64, interval: u64, block_time: i64) -> u64 {
    // interval * block_time in u128 cannot overflow (< 2^127). Capping at i64::MAX means a
    // huge `interval` can no longer wrap negative when cast; `params_ok` keeps real configs
    // below i64::MAX / 4, where nothing below saturates either.
    let expected = ((interval as u128) * (block_time.max(0) as u128)).clamp(1, i64::MAX as u128) as i64;
    let actual = elapsed.clamp((expected / MAX_ADJUST).max(1), expected.saturating_mul(MAX_ADJUST));
    let new = (old as u128) * (actual as u128) / (expected as u128);
    new.clamp(1, u64::MAX as u128) as u64
}

#[derive(AnchorSerialize, AnchorDeserialize, Clone)]
pub struct InitParams {
    /// Reward for the first era, in base units (9 decimals).
    pub initial_reward: u64,
    pub halving_interval: u64,
    pub retarget_interval: u64,
    /// Seconds.
    pub target_block_time: i64,
    /// Starting target: a solution needs work_value(hash) <= target.
    pub initial_target: u64,
    pub max_supply: u64,
}

#[account]
#[derive(InitSpace)]
pub struct Config {
    pub authority: Pubkey,
    pub mint: Pubkey,
    pub bump: u8,
    pub mint_bump: u8,
    pub challenge: [u8; 32],
    pub target: u64,
    pub initial_reward: u64,
    pub halving_interval: u64,
    pub retarget_interval: u64,
    pub target_block_time: i64,
    pub max_supply: u64,
    pub blocks_mined: u64,
    pub total_minted: u64,
    pub epoch_start_ts: i64,
    pub last_solve_ts: i64,
    pub last_miner: Pubkey,
    pub last_reward: u64,
}

#[derive(Accounts)]
pub struct Initialize<'info> {
    #[account(mut)]
    pub authority: Signer<'info>,
    #[account(init, payer = authority, space = 8 + Config::INIT_SPACE, seeds = [CONFIG_SEED], bump)]
    pub config: Account<'info, Config>,
    #[account(
        init,
        payer = authority,
        seeds = [MINT_SEED],
        bump,
        mint::decimals = DECIMALS,
        mint::authority = config,
    )]
    pub mint: Account<'info, Mint>,
    #[account(constraint = program.programdata_address()? == Some(program_data.key()))]
    pub program: Program<'info, crate::program::Sumofrog>,
    #[account(constraint = program_data.upgrade_authority_address == Some(authority.key()) @ SumoError::NotUpgradeAuthority)]
    pub program_data: Account<'info, ProgramData>,
    pub token_program: Program<'info, Token>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct CreateMetadata<'info> {
    #[account(mut)]
    pub authority: Signer<'info>,
    #[account(seeds = [CONFIG_SEED], bump = config.bump, has_one = authority, has_one = mint)]
    pub config: Account<'info, Config>,
    #[account(mut)]
    pub mint: Account<'info, Mint>,
    /// CHECK: PDA derived and checked by the Metaplex program.
    #[account(
        mut,
        seeds = [b"metadata", token_metadata_program.key().as_ref(), mint.key().as_ref()],
        bump,
        seeds::program = token_metadata_program.key()
    )]
    pub metadata: UncheckedAccount<'info>,
    pub token_metadata_program: Program<'info, Metadata>,
    pub system_program: Program<'info, System>,
    pub rent: Sysvar<'info, Rent>,
}

#[derive(Accounts)]
pub struct Mine<'info> {
    #[account(mut)]
    pub miner: Signer<'info>,
    #[account(mut, seeds = [CONFIG_SEED], bump = config.bump, has_one = mint)]
    pub config: Account<'info, Config>,
    #[account(mut, seeds = [MINT_SEED], bump = config.mint_bump)]
    pub mint: Account<'info, Mint>,
    #[account(
        init_if_needed,
        payer = miner,
        associated_token::mint = mint,
        associated_token::authority = miner,
    )]
    pub miner_ata: Account<'info, TokenAccount>,
    pub token_program: Program<'info, Token>,
    pub associated_token_program: Program<'info, AssociatedToken>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct MineTo<'info> {
    /// Fee payer. Signs, pays the fees and (once) the payout wallet's token account rent.
    #[account(mut)]
    pub miner: Signer<'info>,
    /// CHECK: any wallet's public address. It never signs and is only used as the owner of the
    /// token account below and inside the proof-of-work hash.
    pub payout: UncheckedAccount<'info>,
    #[account(mut, seeds = [CONFIG_SEED], bump = config.bump, has_one = mint)]
    pub config: Account<'info, Config>,
    #[account(mut, seeds = [MINT_SEED], bump = config.mint_bump)]
    pub mint: Account<'info, Mint>,
    #[account(
        init_if_needed,
        payer = miner,
        associated_token::mint = mint,
        associated_token::authority = payout,
    )]
    pub payout_ata: Account<'info, TokenAccount>,
    pub token_program: Program<'info, Token>,
    pub associated_token_program: Program<'info, AssociatedToken>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct SetSchedule<'info> {
    pub authority: Signer<'info>,
    #[account(mut, seeds = [CONFIG_SEED], bump = config.bump)]
    pub config: Account<'info, Config>,
    #[account(constraint = program.programdata_address()? == Some(program_data.key()))]
    pub program: Program<'info, crate::program::Sumofrog>,
    #[account(constraint = program_data.upgrade_authority_address == Some(authority.key()) @ SumoError::NotUpgradeAuthority)]
    pub program_data: Account<'info, ProgramData>,
}

#[event]
pub struct ScheduleChanged {
    pub block: u64,
    pub old_reward: u64,
    pub new_reward: u64,
    pub old_halving_interval: u64,
    pub new_halving_interval: u64,
}

#[event]
pub struct BlockMined {
    pub block: u64,
    pub miner: Pubkey,
    pub nonce: u64,
    pub reward: u64,
    pub total_minted: u64,
    pub target: u64,
    pub timestamp: i64,
}

#[event]
pub struct Retargeted {
    pub block: u64,
    pub elapsed: i64,
    pub old_target: u64,
    pub new_target: u64,
}

#[error_code]
pub enum SumoError {
    #[msg("Invalid setup parameters")]
    BadParams,
    #[msg("Only the program upgrade authority can initialize")]
    NotUpgradeAuthority,
    #[msg("Challenge has moved on: someone else found this block, fetch the new one")]
    StaleChallenge,
    #[msg("Hash does not meet the difficulty target")]
    InsufficientWork,
    #[msg("Max supply reached: no more SUMO can be mined")]
    SupplyExhausted,
    #[msg("Counter overflow")]
    MathOverflow,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn halving() {
        assert_eq!(block_reward(50, 100, 0), 50);
        assert_eq!(block_reward(50, 100, 99), 50);
        assert_eq!(block_reward(50, 100, 100), 25);
        assert_eq!(block_reward(50, 100, 6400), 0);
    }

    #[test]
    fn retarget_clamps() {
        // 10 blocks planned for 600s.
        assert_eq!(retarget(1000, 600, 10, 60), 1000);
        assert_eq!(retarget(1000, 300, 10, 60), 500); // twice as fast -> twice as hard
        assert_eq!(retarget(1000, 1, 10, 60), 250); // clamped to 4x harder
        assert_eq!(retarget(1000, 100_000, 10, 60), 4000); // clamped to 4x easier
        assert_eq!(retarget(u64::MAX, 100_000, 10, 60), u64::MAX);
        assert_eq!(retarget(1, 0, 10, 60), 1);
    }

    // ---- golden vectors from scripts/gen_vectors.py (Python is the spec) ----
    use serde_json::Value;

    fn vectors() -> Value {
        let path = concat!(env!("CARGO_MANIFEST_DIR"), "/../../tests/vectors/golden.json");
        serde_json::from_str(&std::fs::read_to_string(path).expect("run scripts/gen_vectors.py")).unwrap()
    }
    fn set<'a>(v: &'a Value, name: &str) -> &'a Vec<Value> {
        let a = v[name].as_array().unwrap();
        assert!(!a.is_empty(), "no {name} vectors");
        a
    }
    fn n<T: std::str::FromStr>(v: &Value, k: &str) -> T
    where
        T::Err: std::fmt::Debug,
    {
        v[k].as_str().unwrap().parse().unwrap()
    }
    fn h32(v: &Value, k: &str) -> [u8; 32] {
        let s = v[k].as_str().unwrap();
        let mut out = [0u8; 32];
        for (i, b) in out.iter_mut().enumerate() {
            *b = u8::from_str_radix(&s[2 * i..2 * i + 2], 16).unwrap();
        }
        out
    }

    #[test]
    fn golden_work_value() {
        for t in set(&vectors(), "work_value") {
            assert_eq!(work_value(&h32(t, "hash")), n::<u64>(t, "expected"), "{t}");
        }
    }

    #[test]
    fn golden_pow_hash() {
        for t in set(&vectors(), "pow_hash") {
            let h = pow_hash(&h32(t, "challenge"), &Pubkey::new_from_array(h32(t, "miner")), n(t, "nonce"));
            assert_eq!(h, h32(t, "hash"), "{t}");
            assert_eq!(work_value(&h), n::<u64>(t, "work_value"), "{t}");
        }
    }

    #[test]
    fn golden_challenges() {
        let v = vectors();
        for t in set(&v, "next_challenge") {
            let c = next_challenge(&h32(t, "solution_hash"), n(t, "slot"), n(t, "blocks_mined"));
            assert_eq!(c, h32(t, "expected"), "{t}");
        }
        for t in set(&v, "genesis_challenge") {
            let c = genesis_challenge(&Pubkey::new_from_array(h32(t, "mint")), n(t, "slot"), n(t, "unix_ts"));
            assert_eq!(c, h32(t, "expected"), "{t}");
        }
    }

    #[test]
    fn golden_block_reward() {
        for t in set(&vectors(), "block_reward") {
            let got = block_reward(n(t, "initial"), n(t, "halving_interval"), n(t, "blocks_mined"));
            assert_eq!(got, n::<u64>(t, "expected"), "{t}");
        }
    }

    #[test]
    fn golden_retarget() {
        for t in set(&vectors(), "retarget") {
            let got = retarget(n(t, "old"), n(t, "elapsed"), n(t, "interval"), n(t, "block_time"));
            assert_eq!(got, n::<u64>(t, "expected"), "{t}");
        }
    }

    // ---- guards added 31 Oct 2026 (retarget overflow note) ----
    fn live_params() -> InitParams {
        // The private test network's settings (scripts/setup.ts / README).
        InitParams {
            initial_reward: 50 * 1_000_000_000,
            halving_interval: 210_000,
            retarget_interval: 10,
            target_block_time: 60,
            initial_target: 1 << 36,
            max_supply: 21_000_000 * 1_000_000_000,
        }
    }

    #[test]
    fn params_ok_rules() {
        assert!(params_ok(&live_params()));
        let bad = |f: fn(&mut InitParams)| {
            let mut p = live_params();
            f(&mut p);
            !params_ok(&p)
        };
        assert!(bad(|p| p.initial_reward = 0));
        assert!(bad(|p| p.halving_interval = 0));
        assert!(bad(|p| p.retarget_interval = 0));
        assert!(bad(|p| p.target_block_time = 0));
        assert!(bad(|p| p.target_block_time = -60));
        assert!(bad(|p| p.initial_target = 0));
        assert!(bad(|p| p.max_supply = p.initial_reward - 1));
        // The overflow guard: a retarget window past i64::MAX / 4 seconds is refused.
        assert!(bad(|p| p.retarget_interval = u64::MAX));
        assert!(bad(|p| p.retarget_interval = 1 << 63));
        assert!(bad(|p| {
            p.retarget_interval = (i64::MAX / 4) as u64 + 1;
            p.target_block_time = 1
        }));
        let mut edge = live_params();
        edge.retarget_interval = (i64::MAX / 4) as u64;
        edge.target_block_time = 1;
        assert!(params_ok(&edge));
    }

    #[test]
    fn retarget_huge_interval_no_longer_wraps() {
        // Before the fix, `interval as i64` wrapped negative for interval > i64::MAX, the
        // window collapsed to 1 s, and a fast epoch made mining 4x EASIER instead of harder.
        let t = 1u64 << 36;
        assert_eq!(retarget(t, 600, u64::MAX, 1), t / 4 - 1);
        assert_eq!(retarget(t, 600, (1 << 63) + 10, 1), t / 4 - 1);
    }

    #[test]
    fn live_schedule_stays_under_cap() {
        let p = live_params();
        let mut total: u128 = 0;
        for era in 0..64u32 {
            total += (p.initial_reward >> era) as u128 * p.halving_interval as u128;
        }
        // 50 SUMO halving every 210,000 blocks pays just under 21M, like Bitcoin.
        assert!(total <= p.max_supply as u128);
        assert!(total > (p.max_supply as u128) * 999 / 1000);
        assert_eq!(capped_reward(p.initial_reward, p.halving_interval, 0, p.max_supply, p.max_supply), 0);
        assert_eq!(capped_reward(p.initial_reward, p.halving_interval, 0, p.max_supply, p.max_supply - 7), 7);
    }

    // ---- yearly halving (1 Nov 2026) ----
    /// The private network's schedule after `set_schedule`: 20 SUMO a block, halving every
    /// 525,600 blocks (365 days at one block a minute). Must match scripts/set-schedule.ts.
    pub const YEARLY_REWARD: u64 = 20 * 1_000_000_000;
    pub const YEARLY_HALVING: u64 = 525_600;

    /// Total ever minted if every block from `history_blocks` on is mined under the yearly
    /// schedule, after `history_blocks` blocks paid `history_reward` each. Era by era, with the
    /// same cap trim as `capped_reward` (whole eras at once, so it runs instantly).
    fn lifetime_issuance(history_blocks: u64, history_reward: u64, max_supply: u64) -> (u64, u64) {
        let mut total = history_blocks * history_reward;
        let mut b = history_blocks;
        loop {
            let r = capped_reward(YEARLY_REWARD, YEARLY_HALVING, b, max_supply, total);
            if r == 0 {
                return (total, b);
            }
            let era_end = (b / YEARLY_HALVING + 1) * YEARLY_HALVING;
            let full = block_reward(YEARLY_REWARD, YEARLY_HALVING, b);
            // blocks that pay the full era reward before the cap bites, at least one
            let n = ((max_supply - total) / full).min(era_end - b).max(1);
            if r < full {
                total += r; // the single trimmed last block
                b += 1;
            } else {
                total += full * n;
                b += n;
            }
            assert!(total <= max_supply);
        }
    }

    #[test]
    fn yearly_schedule_never_passes_21m() {
        let p = live_params();
        // 34 blocks (1,700 SUMO) were mined at 50 before the change; allow for many more.
        for history in [0u64, 34, 35, 100, 1_000, 10_000] {
            let (total, last_block) = lifetime_issuance(history, p.initial_reward, p.max_supply);
            assert_eq!(total, p.max_supply, "history {history}");
            assert!(last_block < 64 * YEARLY_HALVING);
        }
        // Without the cap the yearly schedule would ask for 21,024,000 + 30 per early block,
        // so the cap (not luck) is what holds the line: check it trims rather than overshoots.
        let uncapped: u128 = (0..64u32).map(|e| (YEARLY_REWARD >> e) as u128 * YEARLY_HALVING as u128).sum();
        assert!(uncapped > p.max_supply as u128);
        assert_eq!(capped_reward(YEARLY_REWARD, YEARLY_HALVING, 34, p.max_supply, p.max_supply - 3), 3);
        assert_eq!(block_reward(YEARLY_REWARD, YEARLY_HALVING, 34), 20 * 1_000_000_000);
        assert_eq!(block_reward(YEARLY_REWARD, YEARLY_HALVING, YEARLY_HALVING), 10 * 1_000_000_000);
    }

    /// The private network's settings before 1 Nov: 50 SUMO, halving every 210,000 blocks.
    const OLD_HALVING: u64 = 210_000;

    #[test]
    fn schedule_ok_rules() {
        let (cur, mined, cap) = (YEARLY_REWARD, 40u64, 21_000_000 * 1_000_000_000u64);
        assert!(schedule_ok(cur, YEARLY_HALVING, mined, cap, cur, YEARLY_HALVING)); // no change
        assert!(schedule_ok(cur, YEARLY_HALVING, mined, cap, cur / 2, YEARLY_HALVING)); // lower reward
        assert!(schedule_ok(cur, YEARLY_HALVING, mined, cap, cur, YEARLY_HALVING / 2)); // halving sooner, at most 2x
        assert!(!schedule_ok(cur, YEARLY_HALVING, mined, cap, cur, YEARLY_HALVING / 2 - 1)); // more than 2x sooner
        assert!(!schedule_ok(cur, YEARLY_HALVING, mined, cap, cur + 1, YEARLY_HALVING)); // reward can't go up
        assert!(!schedule_ok(cur, YEARLY_HALVING, mined, cap, cur, YEARLY_HALVING + 1)); // halving can't move later
        assert!(!schedule_ok(cur, YEARLY_HALVING, mined, cap, 0, YEARLY_HALVING));
        assert!(!schedule_ok(cur, YEARLY_HALVING, mined, cap, cur, mined)); // would jump to era 1
        assert!(!schedule_ok(cur, YEARLY_HALVING, mined, cap, cur, 0));
        assert!(!schedule_ok(cur, YEARLY_HALVING, mined, 10, 11, YEARLY_HALVING)); // over the cap
        // The 1 Nov change (50 every 210,000 -> 20 every 525,600) would now be refused: by
        // block 420,000 the old schedule paid 12.5 and the new one would still pay 20.
        assert!(!schedule_ok(50 * 1_000_000_000, OLD_HALVING, 34, cap, YEARLY_REWARD, YEARLY_HALVING));
    }

    #[test]
    fn schedule_cant_undo_a_halving() {
        // Ribbit's attack (proven on localnet, 2 Nov): after the first halving (10 SUMO a block)
        // set 20 SUMO again with the halving point moved just ahead. Refused now.
        let cap = 21_000_000 * 1_000_000_000u64;
        let mined = YEARLY_HALVING + 5; // era 1, paying 10
        assert_eq!(block_reward(YEARLY_REWARD, YEARLY_HALVING, mined), 10 * 1_000_000_000);
        assert!(!schedule_ok(YEARLY_REWARD, YEARLY_HALVING, mined, cap, YEARLY_REWARD, mined + 1));
        assert!(!schedule_ok(YEARLY_REWARD, YEARLY_HALVING, mined, cap, YEARLY_REWARD, 2 * YEARLY_HALVING));
        // Same reward a block pays today (10), restarted at era 0: still a delayed halving.
        assert!(!schedule_ok(YEARLY_REWARD, YEARLY_HALVING, mined, cap, YEARLY_REWARD / 2, mined + 1));
        // Once halving has started, nothing passes: the schedule is fixed.
        for r in [1, YEARLY_REWARD / 4, YEARLY_REWARD / 2, YEARLY_REWARD] {
            for iv in [1, YEARLY_HALVING, mined, mined + 1, u64::MAX] {
                assert!(!schedule_ok(YEARLY_REWARD, YEARLY_HALVING, mined, cap, r, iv), "{r} {iv}");
            }
        }
    }

    #[test]
    fn schedule_floor_blocks_the_14_step_chain() {
        // Ribbit, 2 Nov (c): halving the interval 14 times, each step "at most half" the current
        // one, walked 525,600 down to 41 (1,639 SUMO ever). With the fixed floor only the first
        // step passes; every later one is refused.
        let cap = 21_000_000 * 1_000_000_000u64;
        let mined = 40u64;
        assert_eq!(MIN_HALVING_INTERVAL * 2, YEARLY_HALVING);
        let mut cur = YEARLY_HALVING;
        let mut accepted = vec![];
        for _ in 0..14 {
            let next = (cur + 1) / 2; // the smallest "at most half" step
            if schedule_ok(YEARLY_REWARD, cur, mined, cap, YEARLY_REWARD, next) {
                accepted.push(next);
                cur = next;
            }
        }
        assert_eq!(accepted, vec![MIN_HALVING_INTERVAL]);
        assert_eq!(cur, MIN_HALVING_INTERVAL);
        // At the floor: no change of interval below it, at any size of step.
        for iv in [MIN_HALVING_INTERVAL - 1, 131_400, 65_700, 41, mined + 1] {
            assert!(!schedule_ok(YEARLY_REWARD, MIN_HALVING_INTERVAL, mined, cap, YEARLY_REWARD, iv), "{iv}");
        }
        // Keeping the floor interval (or lowering only the reward) still passes.
        assert!(schedule_ok(YEARLY_REWARD, MIN_HALVING_INTERVAL, mined, cap, YEARLY_REWARD, MIN_HALVING_INTERVAL));
        assert!(schedule_ok(YEARLY_REWARD, MIN_HALVING_INTERVAL, mined, cap, YEARLY_REWARD / 2, MIN_HALVING_INTERVAL));
        // A longer schedule can still drop straight to the floor in one step only if that's at
        // most half; anything between floor and half is fine too.
        assert!(schedule_ok(YEARLY_REWARD, 400_000, mined, cap, YEARLY_REWARD, MIN_HALVING_INTERVAL));
        // Test chains with a short interval (6 blocks) can only keep it.
        assert!(schedule_ok(YEARLY_REWARD, 6, 0, cap, YEARLY_REWARD, 6));
        for iv in [1u64, 2, 3, 4, 5] {
            assert!(!schedule_ok(YEARLY_REWARD, 6, 0, cap, YEARLY_REWARD, iv), "{iv}");
        }
    }

    #[test]
    fn schedule_refuses_the_41_typo() {
        // Ribbit, 2 Nov (b): 41 typed instead of 525,600 used to pass, halve every 41 blocks,
        // end issuance after ~1,435 blocks (about a day) with under 2,000 SUMO, then lock.
        let cap = 21_000_000 * 1_000_000_000u64;
        let mined = 40u64;
        assert!(!schedule_ok(YEARLY_REWARD, YEARLY_HALVING, mined, cap, YEARLY_REWARD, 41));
        let typo_total: u128 = (0..64u32).map(|e| (YEARLY_REWARD >> e) as u128 * 41).sum();
        assert!(typo_total < 2_000 * 1_000_000_000); // what the typo would have paid in total
        // Any slip of the same kind is refused: a dropped digit, or a few digits typed.
        for iv in [52_560u64, 5_256, 525, 52, 1, YEARLY_HALVING / 2 - 1] {
            assert!(!schedule_ok(YEARLY_REWARD, YEARLY_HALVING, mined, cap, YEARLY_REWARD, iv), "{iv}");
        }
        // The shortest allowed interval still pays out at least half the yearly schedule.
        let shortest = YEARLY_HALVING / 2;
        assert!(schedule_ok(YEARLY_REWARD, YEARLY_HALVING, mined, cap, YEARLY_REWARD, shortest));
        let half_total: u128 = (0..64u32).map(|e| (YEARLY_REWARD >> e) as u128 * shortest as u128).sum();
        assert!(half_total >= 10_000_000 * 1_000_000_000);
        // Odd intervals round the right way: 2 * new must reach the current interval.
        // (Above the floor; below it only the current interval passes, see the floor test.)
        let odd = 2 * MIN_HALVING_INTERVAL + 1;
        assert!(!schedule_ok(YEARLY_REWARD, odd, 0, cap, YEARLY_REWARD, MIN_HALVING_INTERVAL));
        assert!(schedule_ok(YEARLY_REWARD, odd, 0, cap, YEARLY_REWARD, MIN_HALVING_INTERVAL + 1));
        assert!(!schedule_ok(YEARLY_REWARD, 7, 0, cap, YEARLY_REWARD, 4)); // under the floor
        assert!(schedule_ok(YEARLY_REWARD, u64::MAX, 0, cap, YEARLY_REWARD, u64::MAX / 2 + 1)); // no overflow
        assert!(!schedule_ok(YEARLY_REWARD, u64::MAX, 0, cap, YEARLY_REWARD, u64::MAX / 2));
    }

    #[test]
    fn schedule_cant_turn_halving_off() {
        // Ribbit's second attack: "never halve" (an interval so long it never arrives).
        let cap = 21_000_000 * 1_000_000_000u64;
        for mined in [0u64, 34, 1_000, YEARLY_HALVING - 1, YEARLY_HALVING, 3 * YEARLY_HALVING + 7] {
            for r in [1, YEARLY_REWARD / 2, YEARLY_REWARD] {
                assert!(!schedule_ok(YEARLY_REWARD, YEARLY_HALVING, mined, cap, r, u64::MAX));
                assert!(!schedule_ok(YEARLY_REWARD, YEARLY_HALVING, mined, cap, r, YEARLY_HALVING * 2));
            }
        }
        // With the old rule, the cap was reached around block 1,050,000 (~2 years) by repeating
        // the undo; under the allowed schedule the cap takes until year 10 or later.
        let (_, last_block) = lifetime_issuance(0, YEARLY_REWARD, cap);
        assert!(last_block > 9 * YEARLY_HALVING);
    }

    // ---- property / fuzz tests (proptest: thousands of random inputs per run) ----
    use proptest::prelude::*;

    /// The plain-maths rule, exact in u128 whenever the window fits MAX_RETARGET_WINDOW.
    fn retarget_exact(old: u64, elapsed: i64, interval: u64, block_time: i64) -> u64 {
        let e = (interval as i128 * block_time as i128).max(1);
        let a = (elapsed as i128).clamp((e / 4).max(1), e * 4);
        ((old as u128 * a as u128) / e as u128).clamp(1, u64::MAX as u128) as u64
    }

    /// (retarget_interval, target_block_time) pairs that initialize accepts.
    fn window() -> impl Strategy<Value = (u64, i64)> {
        prop_oneof![
            (1u64..=10_000, 1i64..=86_400),
            (1u64..=u32::MAX as u64, 1i64..=u32::MAX as i64 / 8),
            (1i64..=i64::MAX / 4).prop_map(|w| (w as u64, 1)),
        ]
    }

    proptest! {
        #![proptest_config(ProptestConfig { cases: 4096, ..ProptestConfig::default() })]

        #[test]
        fn fuzz_retarget_any_input_is_safe(old: u64, elapsed: i64, interval: u64, bt: i64) {
            // Never panics (overflow-checks are on) and never returns 0 (target 0 = unmineable).
            prop_assert!(retarget(old, elapsed, interval, bt) >= 1);
        }

        #[test]
        fn fuzz_retarget_matches_plain_maths(old in 1u64.., elapsed: i64, (iv, bt) in window()) {
            prop_assert_eq!(retarget(old, elapsed, iv, bt), retarget_exact(old, elapsed, iv, bt));
        }

        #[test]
        fn fuzz_retarget_moves_at_most_4x(old in 4u64.., elapsed: i64, (iv, bt) in window()) {
            let new = retarget(old, elapsed, iv, bt) as u128;
            prop_assert!(new <= old as u128 * 4);
            // The hard side is floor(window / 4), so it can be up to 3/window stronger than 4x
            // (0.5% on the live 600 s window). Always in the miners' disfavour, never easier.
            let e = iv as u128 * bt as u128;
            prop_assert!(new * 4 + 4 >= old as u128 * (e.saturating_sub(3)) / e);
            let on_time = (iv as i128 * bt as i128) as i64;
            prop_assert_eq!(retarget(old, on_time, iv, bt), old);
        }

        #[test]
        fn fuzz_retarget_slower_is_never_harder(old: u64, a: i64, b: i64, (iv, bt) in window()) {
            let (lo, hi) = if a <= b { (a, b) } else { (b, a) };
            prop_assert!(retarget(old, lo, iv, bt) <= retarget(old, hi, iv, bt));
        }

        #[test]
        fn fuzz_reward_never_increases(initial: u64, halving in 1u64.., a: u64, b: u64) {
            let (lo, hi) = if a <= b { (a, b) } else { (b, a) };
            prop_assert!(block_reward(initial, halving, hi) <= block_reward(initial, halving, lo));
        }

        #[test]
        fn fuzz_supply_cap_holds(initial in 1u64..=1_000_000, halving in 1u64..=50, extra in 0u64..=10_000_000) {
            // Mine the whole schedule with small settings: the total never passes the cap,
            // and it reaches the cap exactly whenever the cap is below the schedule's sum.
            let max_supply = initial + extra;
            let (mut total, mut blocks) = (0u64, 0u64);
            loop {
                let r = capped_reward(initial, halving, blocks, max_supply, total);
                if r == 0 { break; }
                total = total.checked_add(r).unwrap();
                blocks += 1;
                prop_assert!(total <= max_supply);
                prop_assert!(blocks <= 64 * halving + 1);
            }
            let schedule: u128 = (0..64u32).map(|e| (initial >> e) as u128 * halving as u128).sum();
            prop_assert_eq!(total as u128, schedule.min(max_supply as u128));
        }

        #[test]
        fn fuzz_schedule_change_never_pays_more_later(
            cur_initial in 1u64..=u64::MAX,
            cur_halving in 1u64..=2_000_000,
            mined in 0u64..=4_000_000,
            new_initial in 0u64..=u64::MAX,
            new_halving in 0u64..=4_000_000,
            ahead in 0u64..=200_000_000,
        ) {
            // Whatever change passes, no block from now on pays more than the current schedule.
            if schedule_ok(cur_initial, cur_halving, mined, u64::MAX, new_initial, new_halving) {
                for b in [mined, mined + ahead, mined + ahead % (new_halving + 1), new_halving, cur_halving, 2 * cur_halving + ahead] {
                    if b < mined { continue; }
                    prop_assert!(
                        block_reward(new_initial, new_halving, b) <= block_reward(cur_initial, cur_halving, b),
                        "block {} pays more after the change", b
                    );
                }
            }
        }

        #[test]
        fn fuzz_schedule_change_never_more_than_halves_the_interval(
            cur_halving in 1u64..=u64::MAX,
            mined in 0u64..=1_000,
            new_halving in 0u64..=u64::MAX,
            r in 1u64..=1_000_000,
        ) {
            // Whatever passes: the interval shrinks by at most half, so issuance can't be cut
            // short by more than half by one mistyped change.
            if schedule_ok(r, cur_halving, mined, u64::MAX, r, new_halving) {
                prop_assert!(new_halving as u128 * 2 >= cur_halving as u128);
            }
            // And just below half is always refused.
            let below = cur_halving / 2 - u64::from(cur_halving % 2 == 0);
            prop_assert!(!schedule_ok(r, cur_halving, mined, u64::MAX, r, below));
        }

        #[test]
        fn fuzz_schedule_chain_never_goes_below_the_floor(
            start in 1u64..=4_000_000,
            steps in proptest::collection::vec(0u64..=4_000_000, 1..20),
        ) {
            // Any run of accepted changes, from any start: the interval never ends below
            // min(start, MIN_HALVING_INTERVAL), however many steps are taken.
            let mut cur = start;
            for iv in steps {
                if schedule_ok(1_000, cur, 0, u64::MAX, 1_000, iv) {
                    cur = iv;
                }
            }
            prop_assert!(cur >= start.min(MIN_HALVING_INTERVAL));
        }

        #[test]
        fn fuzz_schedule_change_from_live_is_never_kinder(
            mined in 0u64..=3_000_000,
            new_initial in 0u64..=40_000_000_000,
            new_halving in 0u64..=2_000_000,
            ahead in 0u64..=40_000_000,
        ) {
            let cap = 21_000_000 * 1_000_000_000u64;
            if schedule_ok(YEARLY_REWARD, YEARLY_HALVING, mined, cap, new_initial, new_halving) {
                prop_assert!(mined < YEARLY_HALVING); // nothing passes after the first halving
                prop_assert!(new_halving <= YEARLY_HALVING);
                prop_assert!(new_halving >= YEARLY_HALVING / 2);
                let b = mined + ahead;
                prop_assert!(block_reward(new_initial, new_halving, b) <= block_reward(YEARLY_REWARD, YEARLY_HALVING, b));
            }
        }

        #[test]
        fn fuzz_work_value_orders_like_the_hash(a: [u8; 32], b: [u8; 32]) {
            // No difficulty bypass: a smaller work value always means a smaller hash prefix.
            prop_assert_eq!(work_value(&a).cmp(&work_value(&b)), a[..8].cmp(&b[..8]));
        }

        #[test]
        fn fuzz_pow_hash_binds_miner_and_nonce(c: [u8; 32], m1: [u8; 32], m2: [u8; 32], n1: u64, n2: u64) {
            // A nonce found for one miner (or one challenge) is useless for another.
            let (p1, p2) = (Pubkey::new_from_array(m1), Pubkey::new_from_array(m2));
            if (m1, n1) != (m2, n2) {
                prop_assert_ne!(pow_hash(&c, &p1, n1), pow_hash(&c, &p2, n2));
            }
            let mut c2 = c;
            c2[0] ^= 1;
            prop_assert_ne!(pow_hash(&c, &p1, n1), pow_hash(&c2, &p1, n1));
        }

        #[test]
        fn fuzz_next_challenge_changes_every_block(sol: [u8; 32], slot: u64, bm in 0u64..u64::MAX) {
            prop_assert_ne!(next_challenge(&sol, slot, bm), next_challenge(&sol, slot, bm + 1));
        }
    }
}
