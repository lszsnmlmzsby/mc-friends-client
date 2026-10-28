// MC 1.20.1 / KubeJS 2001. Install on the server (or in a single-player instance).
// Death retention is configured separately in ageofmythology/death_keep_items.toml.
{
  const BOOK = 'ageofmythology:the_fool_book'
  const RETURNS = 'friendsmc_fool_book_returns'
  const NativeStack = Java.loadClass('net.minecraft.world.item.ItemStack')
  const TagParser = Java.loadClass('net.minecraft.nbt.TagParser')

  function pending(player) {
    const saved = player.persistentData.getString(RETURNS)
    return saved ? JSON.parse(saved) : []
  }

  function savePending(player, stacks) {
    if (stacks.length) player.persistentData.putString(RETURNS, JSON.stringify(stacks))
    else player.persistentData.remove(RETURNS)
  }

  // Restrict insertion to the 36 normal inventory slots. Never spawn leftovers,
  // overwrite an occupied slot, or automatically put a book in an armor slot.
  function insert(player, stack) {
    for (let slot = 0; slot < 36 && !stack.isEmpty(); slot++) {
      stack = player.inventory.insertItem(slot, stack, false)
    }
    return stack
  }

  function ensureBook(player) {
    if (!player.isAlive() || player.isSpectator() || player.isFake()) return

    const saved = pending(player)
    const remaining = []
    for (let i = 0; i < saved.length; i++) {
      const stack = insert(player, NativeStack.of(TagParser.parseTag(saved[i])))
      if (!stack.isEmpty()) remaining.push(String(stack.toNBT()))
    }
    if (saved.length) {
      savePending(player, remaining)
      player.sendInventoryUpdate()
    }
    // An original book awaiting a free slot takes priority over a fresh copy.
    if (remaining.length || player.inventory.find(BOOK) !== -1 ||
        player.offHandItem.id === BOOK || player.mouseItem.id === BOOK) return

    const leftover = insert(player, Item.of(BOOK))
    if (leftover.isEmpty()) player.sendInventoryUpdate()
  }

  ItemEvents.dropped(BOOK, event => {
    const player = event.player
    const original = event.item.copy()
    // Forge has already removed the stack from the inventory at this point.
    // Cancelling alone would destroy it: return the exact stack, including NBT.
    let leftover = insert(player, original)
    if (!leftover.isEmpty() && player.mouseItem.isEmpty()) {
      player.mouseItem = leftover
      leftover = Item.empty
    }
    if (!leftover.isEmpty()) {
      const saved = pending(player)
      saved.push(String(leftover.toNBT()))
      savePending(player, saved)
    }
    player.sendInventoryUpdate()
    player.openInventory.broadcastChanges()
    // KubeJS 2001 cancel() stops this callback immediately, so it must be last.
    event.cancel()
  })

  // Check after login/respawn inventory restoration, once per second per player.
  // No login/respawn handler gives items before other mods restore their slots.
  PlayerEvents.tick(event => {
    if (event.player.tickCount % 20 === 0) ensureBook(event.player)
  })
}
