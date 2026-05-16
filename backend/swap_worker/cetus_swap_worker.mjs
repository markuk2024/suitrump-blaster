import { AggregatorClient } from '@cetusprotocol/aggregator-sdk';
import { SuiClient, getFullnodeUrl } from '@mysten/sui/client';
import { Ed25519Keypair } from '@mysten/sui/keypairs/ed25519';
import { Transaction } from '@mysten/sui/transactions';
import { decodeSuiPrivateKey } from '@mysten/sui/cryptography';
import BN from 'bn.js';

function readJsonArg() {
  const raw = process.argv[2];
  if (!raw) {
    throw new Error('Missing JSON request argument');
  }
  return JSON.parse(raw);
}

function keypairFromPrivateKey(privateKey) {
  if (!privateKey) {
    throw new Error('ADMIN_PRIVATE_KEY is required');
  }

  if (privateKey.startsWith('suiprivkey1')) {
    const decoded = decodeSuiPrivateKey(privateKey);
    return Ed25519Keypair.fromSecretKey(decoded.secretKey);
  }

  const hex = privateKey.replace(/^0x/, '');
  return Ed25519Keypair.fromSecretKey(Buffer.from(hex, 'hex'));
}

function allocateAmounts(total, winners) {
  const totalWeight = winners.reduce((sum, winner) => sum + BigInt(winner.amount), 0n);
  if (totalWeight <= 0n) {
    throw new Error('Winner amount weights must be greater than zero');
  }

  let allocated = 0n;
  return winners.map((winner, index) => {
    let amount = total * BigInt(winner.amount) / totalWeight;
    if (index === winners.length - 1) {
      amount = total - allocated;
    } else {
      allocated += amount;
    }
    return amount.toString();
  });
}

async function main() {
  const request = readJsonArg();
  const rpcUrl = request.rpcUrl || getFullnodeUrl('mainnet');
  const keypair = keypairFromPrivateKey(request.adminPrivateKey || process.env.ADMIN_PRIVATE_KEY);
  const sender = keypair.getPublicKey().toSuiAddress();

  const inputCoinType = request.inputCoinType || '0x2::sui::SUI';
  const targetCoinType = request.targetCoinType;
  if (!targetCoinType) {
    throw new Error('targetCoinType is required');
  }

  const amountIn = new BN(String(request.amountIn));
  const client = new SuiClient({ url: rpcUrl });
  const aggregator = new AggregatorClient({ client });

  const routers = await aggregator.findRouters({
    from: inputCoinType,
    target: targetCoinType,
    amount: amountIn,
    byAmountIn: true,
  });

  if (!routers) {
    throw new Error(`No Cetus route found for ${inputCoinType} -> ${targetCoinType}`);
  }

  const txb = new Transaction();
  txb.setSender(sender);

  const [inputCoin] = txb.splitCoins(txb.gas, [txb.pure.u64(String(request.amountIn))]);
  const targetCoin = await aggregator.routerSwap({
    routers,
    txb,
    inputCoin,
    slippage: Number(request.slippage ?? 0.03),
  });

  if (!request.poolObjectId || !request.packageId || !request.winners?.length) {
    aggregator.transferOrDestoryCoin(txb, targetCoin, targetCoinType);
  } else {
    const expectedOut = BigInt(String(routers.amountOut || routers.outputAmount || routers.returnAmount || 0));
    if (expectedOut <= 0n) {
      aggregator.transferOrDestoryCoin(txb, targetCoin, targetCoinType);
      throw new Error('Cetus route did not expose amountOut; cannot safely allocate SUITRUMP rewards');
    }

    const devFeeBps = BigInt(Math.round(Number(request.devFeePercentage || 0) * 100));
    const devAmount = expectedOut * devFeeBps / 10000n;
    const winnerTotal = expectedOut - devAmount;
    const winnerAmounts = allocateAmounts(winnerTotal, request.winners);
    const winnerAddresses = request.winners.map((winner) => winner.wallet);

    if (devAmount > 0n && request.devWallet) {
      winnerAddresses.unshift(request.devWallet);
      winnerAmounts.unshift(devAmount.toString());
    }

    txb.moveCall({
      target: `${request.packageId}::pool::distribute_external_rewards`,
      typeArguments: [targetCoinType],
      arguments: [
        txb.object(request.poolObjectId),
        targetCoin,
        txb.pure.vector('address', winnerAddresses),
        txb.pure.vector('u64', winnerAmounts),
      ],
    });
  }

  const inspect = await client.devInspectTransactionBlock({
    sender,
    transactionBlock: txb,
  });

  if (inspect.effects?.status?.status !== 'success') {
    throw new Error(`Cetus swap PTB failed inspection: ${JSON.stringify(inspect.effects?.status)}`);
  }

  const result = await client.signAndExecuteTransaction({
    signer: keypair,
    transaction: txb,
    options: {
      showEffects: true,
      showBalanceChanges: true,
      showObjectChanges: true,
    },
  });

  console.log(JSON.stringify({
    status: result.effects?.status?.status === 'success' ? 'success' : 'error',
    digest: result.digest,
    effectsStatus: result.effects?.status,
    balanceChanges: result.balanceChanges || [],
    objectChanges: result.objectChanges || [],
  }));
}

main().catch((error) => {
  console.error(JSON.stringify({
    status: 'error',
    message: error.message,
    stack: error.stack,
  }));
  process.exit(1);
});
