import { NextResponse } from 'next/server'
import { readFile } from 'fs/promises'
import { existsSync } from 'fs'
import { join } from 'path'

// Path to actions log file (relative to project root)
const ACTIONS_FILE = join(process.cwd(), 'actions.json')

export async function GET() {
    try {
        // Check if actions file exists
        if (!existsSync(ACTIONS_FILE)) {
            return NextResponse.json({
                actions: [],
                message: 'No actions logged yet',
            })
        }

        // Read and parse actions file
        const content = await readFile(ACTIONS_FILE, 'utf-8')
        const actions = JSON.parse(content)

        // Return last 50 actions, most recent first
        const recentActions = actions.slice(-50).reverse()

        return NextResponse.json({
            actions: recentActions.map((action: Record<string, unknown>) => ({
                timestamp: action.timestamp,
                type: action.type,
                description: action.description,
                details: action.details,
            })),
        })
    } catch (error) {
        console.error('Error reading actions:', error)
        return NextResponse.json({
            actions: [],
            error: String(error),
        }, { status: 500 })
    }
}
