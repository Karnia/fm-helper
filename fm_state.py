from collections import defaultdict
import pandas as pd
import dofus_protocol as dp


class Item:
	def __init__(self, item_id, stats):
		self.id = item_id
		self._stats = stats

	def __getitem__(self, item):
		return self._stats[item]

	def __setitem__(self, key, value):
		self._stats[key] = value

	def __len__(self):
		return len(self._stats)

	def keys(self):
		return self._stats.keys()


class FMState:
	def __init__(self):
		self.history = []
		self.slots = {}
		self.last_remove = None
		self.pools = defaultdict(float)
		# read the stats.csv here
		self.item_info = pd.read_csv("stats.csv", index_col=0).to_dict("index")

	def read_item(self, pkt: dp.DofusPacket, offset):
		# skip the first or second byte
		i = offset
		if pkt[i] >= 128:
			i += 1
		i += 2
		# read the amount of stats
		count = pkt[i]
		i += 1

		def read_value():
			nonlocal i
			value = pkt[i]
			if value >= 128:
				value += pkt[i+1]*64
				i += 1
			return value

		stats = defaultdict(int)
		while count:
			# skip 1 octet (i still don't know what 26 is for)
			i += 1
			# read whether or not the stat is a unique value
			unique = pkt[i] == 64
			i += 1
			# read the id, for some reason it's on 2 bytes if the first byte is > 128
			stat_id = read_value()
			i += 1
			# read the value
			if unique:
				stats[stat_id] = read_value()
				i += 1
			else:
				min_val = read_value()
				i += 1
				max_val = read_value()
				i += 1
				stats[stat_id] = (min_val, max_val)
			count -= 1
		# read the item unique id
		item_id = pkt[i:i+2]
		return Item(item_id, stats)

	def update(self, pkt: dp.DofusPacket):
		if pkt.id == dp.DofusPacket.ID_START_FM:
			print("opened craft window")
		elif pkt.id == dp.DofusPacket.ID_ADD:
			item = self.read_item(pkt, 4)
			self.slots[item.id] = item
			print(f"added an item/rune {item}")
			print(pkt)
		elif pkt.id == dp.DofusPacket.ID_REMOVED:
			item_id = pkt[-5:-3]
			if item_id in self.slots:
				self.last_remove = self.slots[item_id]
			self.slots.pop(item_id, None)
			print(f"removed item/rune {item_id}")
			print(pkt)
		elif pkt.id == dp.DofusPacket.ID_FM_ITEM:
			# retrieve the item
			new_item = self.read_item(pkt, 2)
			# retrieve the old item
			old_item = self.slots[new_item.id]
			self.slots[new_item.id] = new_item
			# retrieve the rune
			keys = list(self.slots.keys())
			keys.remove(new_item.id)
			if keys:
				rune = self.slots[keys[0]]
			else:
				rune = self.last_remove
			# compute the delta stats
			delta_stats = {}
			poids = {}
			for stat in set(new_item.keys()) | set(old_item.keys()):
				if stat in self.item_info:
					statname = self.item_info[stat]["name"]
					new_stat = new_item[stat] - old_item[stat]
					if new_stat:
						delta_stats[statname] = new_stat
						poids[statname] = self.item_info[stat]["poids"]
			# compute the delta pool
			if pkt[-1] == 1:
				# the pool didn't change
				delta_pool = 0
			else:
				# the pool did change
				delta_pool = -sum(delta*poids[stat] for stat, delta in delta_stats.items())
				# TODO: verifier le delire ou y a marque +reliquat mais en fait non
				if pkt[0] != 2:
					# it was a failure, we pay the rune cost
					delta_pool -= rune[list(rune.keys())[0]]

			self.pools[new_item["id"]] += delta_pool
			if self.pools[new_item["id"]] < 0:
				self.pools[new_item["id"]] = 0
			print(f"FM'ed item - new pool {self.pools[new_item['id']]} - delta {delta_stats} ")
			print(pkt)
