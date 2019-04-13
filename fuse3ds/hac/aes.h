/*
 *
 * Chinese Academy of Sciences
 * State Key Laboratory of Information Security
 * Institute of Information Engineering
 *
 * Copyright (C) 2016 Chinese Academy of Sciences
 *
 * LuoPeng, luopeng@iie.ac.cn
 * Updated in May 2016
 *
 */
#ifndef AES_128_H
#define AES_128_H

#include <stdio.h>
#include <stdint.h>

#define AES_BLOCK_SIZE      16
#define AES_ROUNDS          10  // 12, 14
#define AES_ROUND_KEY_SIZE  176 // AES-128 has 10 rounds, and there is a AddRoundKey before first round. (10+1)x16=176.

/**
 * @purpose:            Key schedule for AES-128
 * @par[in]key:         16 bytes of master keys
 * @par[out]roundkeys:  176 bytes of round keys
 */
void aes_key_schedule_128(const uint8_t *key, uint8_t *roundkeys);

/**
 * @purpose:            Encryption. The length of plain and cipher should be one block (16 bytes).
 *                      The plaintext and ciphertext may point to the same memory
 * @par[in]roundkeys:   round keys
 * @par[in]plaintext:   plain text
 * @par[out]ciphertext: cipher text
 */
void aes_encrypt_128(const uint8_t *roundkeys, const uint8_t *plaintext, uint8_t *ciphertext);

/**
 * @purpose:            Decryption. The length of plain and cipher should be one block (16 bytes).
 *                      The ciphertext and plaintext may point to the same memory
 * @par[in]roundkeys:   round keys
 * @par[in]ciphertext:  cipher text
 * @par[out]plaintext:  plain text
 */
void aes_decrypt_128(const uint8_t *roundkeys, const uint8_t *ciphertext, uint8_t *plaintext);

#endif
