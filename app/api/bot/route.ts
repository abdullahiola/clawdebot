import { NextResponse } from 'next/server'
import { readFile } from 'fs/promises'
import { existsSync } from 'fs'
import { join } from 'path'

// Path to bot state file (relative to project root)
const STATE_FILE = join(process.cwd(), 'monitor_state.json')

export async function GET() {
  try {
    // Check if state file exists
    if (!existsSync(STATE_FILE)) {
      return NextResponse.json({
        connected: false,
        message: 'Bot state file not found. Is the bot running?',
        state: null,
      }, { status: 200 })
    }

    // Read and parse state file
    const content = await readFile(STATE_FILE, 'utf-8')
    const state = JSON.parse(content)

    return NextResponse.json({
      connected: true,
      state: {
        tokenAddress: state.token_address,
        totalBuys: state.total_buys || 0,
        totalSells: state.total_sells || 0,
        totalBuyVolume: state.total_buy_volume || 0,
        totalSellVolume: state.total_sell_volume || 0,
        lastPrice: state.last_price,
        highestPrice: state.highest_price,
        lowestPrice: state.lowest_price,
        lastMarketCap: state.last_market_cap,
        lastHolderCount: state.last_holder_count,
        lastCreatorRewardsAvailable: state.last_creator_rewards_available || 0,
        creatorRewards: state.creator_rewards || 0,
        totalAnalyses: state.total_analyses || 0,
        totalAlerts: state.total_alerts || 0,
        startTime: state.start_time,
        analysisMode: state.analysis_mode || 'brief',
      },
    })
  } catch (error) {
    console.error('Error reading bot state:', error)
    return NextResponse.json({
      connected: false,
      message: 'Error reading bot state',
      error: String(error),
    }, { status: 500 })
  }
}
