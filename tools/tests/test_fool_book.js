// Behavioral tests with KubeJS/Forge API doubles, not a replacement for an in-game test.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const BOOK = 'ageofmythology:the_fool_book'
const RETURNS = 'friendsmc_fool_book_returns'
const CANCEL = Symbol('KubeJS EventExit')
const handlers = {}

function stack(id = 'minecraft:air', count = 0, nbt = null) {
  return {
    id, count, nbt,
    isEmpty() { return this.count === 0 },
    copy() { return stack(this.id, this.count, structuredClone(this.nbt)) },
    toNBT() { return JSON.stringify({ id: this.id, count: this.count, nbt: this.nbt }) },
  }
}
const empty = () => stack()
const context = {
  Java: { loadClass(name) {
    if (name === 'net.minecraft.world.item.ItemStack') return {
      of(value) { const { id, count, nbt } = value; return stack(id, count, nbt) },
    }
    if (name === 'net.minecraft.nbt.TagParser') return { parseTag: JSON.parse }
    throw Error('Unexpected Java class: ' + name)
  } },
  Item: { of: id => stack(id, 1), get empty() { return empty() } },
  ItemEvents: { dropped(id, fn) { handlers.dropId = id; handlers.drop = fn } },
  PlayerEvents: { tick(fn) { handlers.tick = fn } },
}
vm.runInNewContext(fs.readFileSync(path.join(__dirname,
  '../../packs/fool/overrides/kubejs/server_scripts/friendsmc_fool_book.js'), 'utf8'), context)

function player(full = false) {
  const slots = Array.from({ length: 41 }, (_, i) => full && i < 36 ? stack('minecraft:stone', 64) : empty())
  const data = new Map()
  return {
    slots, data, tickCount: 20, alive: true, spectator: false, fake: false,
    mouseItem: empty(),
    get offHandItem() { return slots[40] },
    isAlive() { return this.alive },
    isSpectator() { return this.spectator },
    isFake() { return this.fake },
    persistentData: {
      getString: key => data.get(key) || '',
      putString: (key, value) => data.set(key, value),
      remove: key => data.delete(key),
    },
    inventory: {
      find: id => slots.findIndex(s => !s.isEmpty() && s.id === id),
      insertItem(slot, incoming, simulate) {
        assert.equal(simulate, false)
        assert.ok(slot < 36, 'never insert in armor/offhand')
        if (slots[slot].isEmpty()) {
          slots[slot] = stack(incoming.id, 1, structuredClone(incoming.nbt))
          return incoming.count === 1 ? empty() : stack(incoming.id, incoming.count - 1, incoming.nbt)
        }
        return incoming
      },
    },
    sendInventoryUpdate() {},
    openInventory: { broadcastChanges() {} },
    give() { throw Error('give() could spawn items on the ground') },
  }
}
const tick = p => handlers.tick({ player: p })
const books = p => p.slots.filter(s => s.id === BOOK).reduce((n, s) => n + s.count, 0)
function drop(p, item) {
  let cancelled = false
  try {
    // Forge has already removed the tossed stack before firing this callback.
    handlers.drop({ player: p, item, cancel() { cancelled = true; throw CANCEL } })
  } catch (error) { if (error !== CANCEL) throw error }
  assert.ok(cancelled, 'drop must be cancelled after restoration')
}

assert.equal(handlers.dropId, BOOK)
{
  const p = player()
  p.tickCount = 1; tick(p); assert.equal(books(p), 0)
  p.tickCount = 20
  for (let i = 0; i < 50; i++) tick(p)
  assert.equal(books(p), 1, 'one book only')
  p.slots[0] = empty(); tick(p)
  assert.equal(books(p), 1, 'replenish after removal')
}
for (const location of ['offhand', 'cursor']) {
  const p = player()
  if (location === 'offhand') p.slots[40] = stack(BOOK, 1)
  else p.mouseItem = stack(BOOK, 1)
  tick(p)
  assert.equal(books(p), location === 'offhand' ? 1 : 0)
}
for (const field of ['alive', 'spectator', 'fake']) {
  const p = player()
  p[field] = field !== 'alive'
  tick(p); assert.equal(books(p), 0, field)
}
{
  const p = player(true)
  for (let i = 0; i < 100; i++) tick(p)
  assert.equal(books(p), 0, 'full inventory must not overwrite items or fill equipment')
  assert.ok(p.mouseItem.isEmpty())
  p.slots[12] = empty(); tick(p); tick(p)
  assert.equal(books(p), 1)
}
{
  const p = player()
  const nbt = { display: { Name: 'custom book' }, progress: { stage: 9 } }
  drop(p, stack(BOOK, 1, nbt))
  tick(p)
  assert.equal(books(p), 1)
  assert.deepEqual(p.slots[0].nbt, nbt, 'return the original NBT')
}
{
  const p = player(true)
  drop(p, stack(BOOK, 1, { custom: 'cursor return' }))
  tick(p)
  assert.equal(books(p), 0)
  assert.equal(p.mouseItem.id, BOOK)
  assert.equal(p.mouseItem.nbt.custom, 'cursor return')
}
{
  const p = player(true)
  p.mouseItem = stack('minecraft:diamond', 5)
  drop(p, stack(BOOK, 2, { custom: 'pending original' }))
  tick(p)
  assert.ok(p.data.has(RETURNS), 'keep original stack until there is room')
  assert.equal(p.mouseItem.count, 5, 'never replace an occupied cursor')
  // KubeJS copies persistentData on respawn. Simulate that with a fresh player.
  const afterRespawn = player(true)
  afterRespawn.data.set(RETURNS, p.data.get(RETURNS))
  afterRespawn.slots[3] = empty(); tick(afterRespawn)
  assert.equal(books(afterRespawn), 1)
  assert.ok(afterRespawn.data.has(RETURNS), 'partial return retains the remainder')
  afterRespawn.slots[5] = empty(); tick(afterRespawn); tick(afterRespawn)
  assert.equal(books(afterRespawn), 2)
  assert.equal(afterRespawn.slots[3].nbt.custom, 'pending original')
  assert.ok(!afterRespawn.data.has(RETURNS))
}
console.log('Fool book behavioral checks passed (mock KubeJS API).')
