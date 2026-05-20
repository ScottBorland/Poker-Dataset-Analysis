import { NumPlayersNode } from './NumPlayersNode'
import { HoleCardsNode } from './HoleCardsNode'
import { ShowdownNode } from './ShowdownNode'
import { FlopTypeNode } from './FlopTypeNode'
import { PreflopActionNode } from './PreflopActionNode'
import { PlayerNode } from './PlayerNode'
import { PlayerPositionNode } from './PlayerPositionNode'
import { StatsNode } from './StatsNode'

export const nodeTypes = {
  numPlayers: NumPlayersNode,
  holeCards: HoleCardsNode,
  showdown: ShowdownNode,
  flopType: FlopTypeNode,
  preflopAction: PreflopActionNode,
  playerName: PlayerNode,
  playerPosition: PlayerPositionNode,
  stats: StatsNode,
}
