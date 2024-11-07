"""A parser for the Mozilla variant of Snappy frame format."""
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
# Credits:
#   – Python source code by Erin Yuki Schlarb, 2024.

import collections.abc as cabc
import io
import typing as ty

import cramjam


def decompress_raw(data: bytes) -> bytes:
	"""Decompress a raw Snappy chunk without any framing"""
	# Delegate this part to the cramjam library
	return cramjam.snappy.decompress_raw(data)


class Decompressor(io.BufferedIOBase):
	inner: io.BufferedIOBase
	
	_buf: bytearray
	_buf_len: int
	_buf_pos: int
	
	def __init__(self, inner: io.BufferedIOBase) -> None:
		assert inner.readable()
		self.inner = inner
		self._buf = bytearray(65536)
		self._buf_len = 0
		self._buf_pos = 0
	
	def readable(self) -> ty.Literal[True]:
		return True
	
	def _read_next_data_chunk(self) -> None:
		# We start with the buffer empty
		assert self._buf_len == 0
		
		# Keep parsing chunks until something is added to the buffer
		while self._buf_len == 0:
			# Read chunk header
			header = self.inner.read(4)
			if len(header) == 0:
				# EOF – buffer remains empty
				return
			elif len(header) != 4:
				# Just part of a header being present is invalid
				raise EOFError("Unexpected EOF while reading Snappy chunk header")
			type, length = header[0], int.from_bytes(header[1:4], "little")
			
			if type == 0xFF:
				# Stream identifier – contents should be checked but otherwise ignored
				if length != 6:
					raise ValueError("Invalid stream identifier (wrong length)")
				
				# Read and verify required content is present
				content = self.inner.read(length)
				if len(content) != 6:
					raise EOFError("Unexpected EOF while reading stream identifier")
				
				if content != b"sNaPpY":
					raise ValueError("Invalid stream identifier (wrong content)")
			elif type == 0x00:
				# Compressed data
				
				# Read checksum
				checksum: bytes = self.inner.read(4)
				if len(checksum) != 4:
					raise EOFError("Unexpected EOF while reading data checksum")
				
				# Read compressed data into new buffer
				compressed: bytes = self.inner.read(length - 4)
				if len(compressed) != length - 4:
					raise EOFError("Unexpected EOF while reading data contents")
				
				# Decompress data into inner buffer
				#XXX: There does not appear to an efficient way to set the length
				#     of a bytearray
				self._buf_len = cramjam.snappy.decompress_raw_into(compressed, self._buf)
				
				#TODO: Verify checksum
			elif type == 0x01:
				# Uncompressed data
				if length > 65536:
					raise ValueError("Invalid uncompressed data chunk (length > 65536)")
				
				checksum: bytes = self.inner.read(4)
				if len(checksum) != 4:
					raise EOFError("Unexpected EOF while reading data checksum")
				
				# Read chunk data into buffer
				with memoryview(self._buf) as view:
					if self.inner.readinto(view[:(length - 4)]) != length - 4:
						raise EOFError("Unexpected EOF while reading data contents")
					self._buf_len = length - 4
				
				#TODO: Verify checksum
			elif type in range(0x80, 0xFE + 1):
				# Padding and reserved skippable chunks – just skip the contents
				if self.inner.seekable():
					self.inner.seek(length, io.SEEK_CUR)
				else:
					self.inner.read(length)
			else:
				raise ValueError(f"Unexpected unskippable reserved chunk: 0x{type:02X}")
	
	def read1(self, size: ty.Optional[int] = -1) -> bytes:
		# Read another chunk if the buffer is currently empty
		if self._buf_len < 1:
			self._read_next_data_chunk()
		
		# Return some of the data currently present in the buffer
		start = self._buf_pos
		if size is None or size < 0:
			end = self._buf_len
		else:
			end = min(start + size, self._buf_len)
		
		result: bytes = bytes(self._buf[start:end])
		if end < self._buf_len:
			self._buf_pos = end
		else:
			self._buf_len = 0
			self._buf_pos = 0
		return result
	
	def read(self, size: ty.Optional[int] = -1) -> bytes:
		buf: bytearray = bytearray()
		if size is None or size < 0:
			while (data := self.read1()) > 0:
				buf += data
		else:
			while len(buf) < size and (data := self.read1(size - len(buf))) > 0:
				buf += data
		return buf
	
	def readinto1(self, buf: cabc.Sequence[bytes]) -> int:
		# Read another chunk if the buffer is currently empty
		if self._buf_len < 1:
			self._read_next_data_chunk()
		
		# Copy some of the data currently present in the buffer
		start = self._buf_pos
		end = min(start + len(buf), self._buf_len)
		
		buf[0:(end - start)] = self._buf[start:end]
		if end < self._buf_len:
			self._buf_pos = end
		else:
			self._buf_len = 0
			self._buf_pos = 0
		return end - start
	
	def readinto(self, buf: cabc.Sequence[bytes]) -> int:
		with memoryview(buf) as view:
			pos = 0
			while pos < len(buf) and (length := self.readinto1(view[pos:])) > 0:
				pos += length
			return pos
