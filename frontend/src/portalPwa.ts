/**
 * PWA do Portal do Colaborador: manifesto, service worker e Web Push.
 *
 * Só o portal usa isto (o painel e o telão não registram nada). O service
 * worker não intercepta requisições nem guarda cache: só recebe o push e abre
 * o cartão ao tocar na notificação. Tudo é opcional: sem suporte ou sem
 * permissão, o portal funciona normalmente com os avisos em tempo real.
 */

import { requisitar } from './api'
import type { PushStatus } from './types'

const SW = '/sw-portal.js'

/** Liga o manifesto do portal (instalar na tela de início). */
export function ativarManifestoPortal(): void {
  if (document.querySelector('link[rel="manifest"]')) return
  const link = document.createElement('link')
  link.rel = 'manifest'
  link.href = '/manifest-portal.json'
  document.head.appendChild(link)
}

export function ehIos(): boolean {
  const ua = navigator.userAgent
  return /iPad|iPhone|iPod/.test(ua) || (ua.includes('Macintosh') && navigator.maxTouchPoints > 1)
}

export function instaladoNaTelaInicial(): boolean {
  return (
    window.matchMedia?.('(display-mode: standalone)').matches ||
    (navigator as Navigator & { standalone?: boolean }).standalone === true
  )
}

export type SuportePush =
  | { ok: true }
  | { ok: false; motivo: 'sem_https' | 'ios_instalar' | 'navegador' | 'negado' }

/** O que este aparelho/navegador permite agora. */
export function suportePush(): SuportePush {
  if (!window.isSecureContext) return { ok: false, motivo: 'sem_https' }
  if (ehIos() && !instaladoNaTelaInicial()) return { ok: false, motivo: 'ios_instalar' }
  if (!('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window)) {
    return { ok: false, motivo: 'navegador' }
  }
  if (Notification.permission === 'denied') return { ok: false, motivo: 'negado' }
  return { ok: true }
}

function chaveParaBytes(base64url: string): Uint8Array {
  const preenchido = base64url + '='.repeat((4 - (base64url.length % 4)) % 4)
  const binario = atob(preenchido.replace(/-/g, '+').replace(/_/g, '/'))
  return Uint8Array.from(binario, (c) => c.charCodeAt(0))
}

async function registro(): Promise<ServiceWorkerRegistration> {
  const atual = await navigator.serviceWorker.getRegistration('/')
  if (atual) return atual
  return navigator.serviceWorker.register(SW, { scope: '/' })
}

/** Inscrição deste aparelho, se houver. */
export async function inscricaoAtual(): Promise<PushSubscription | null> {
  if (suportePush().ok !== true) return null
  const reg = await navigator.serviceWorker.getRegistration('/')
  return (await reg?.pushManager.getSubscription()) ?? null
}

/** Pede permissão (só depois de um toque do colaborador) e inscreve o aparelho. */
export async function ativarPush(status: PushStatus): Promise<PushStatus> {
  if (!status.disponivel || !status.chave_publica) throw new Error(status.motivo ?? 'Indisponível no servidor')
  const permissao = await Notification.requestPermission()
  if (permissao !== 'granted') throw new Error('Permissão de notificações não concedida.')
  const reg = await registro()
  await navigator.serviceWorker.ready
  let inscricao = await reg.pushManager.getSubscription()
  if (!inscricao) {
    inscricao = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: chaveParaBytes(status.chave_publica),
    })
  }
  const dados = inscricao.toJSON()
  return requisitar<PushStatus>('/api/minha-area/push/inscricao', {
    metodo: 'POST',
    corpo: { endpoint: dados.endpoint, p256dh: dados.keys?.p256dh, auth: dados.keys?.auth },
  })
}

/** Desativa as notificações deste aparelho (no navegador e no servidor). */
export async function desativarPush(): Promise<PushStatus | null> {
  const inscricao = await inscricaoAtual()
  if (!inscricao) return null
  const endpoint = inscricao.endpoint
  await inscricao.unsubscribe().catch(() => undefined)
  return requisitar<PushStatus>('/api/minha-area/push/cancelar', { metodo: 'POST', corpo: { endpoint } })
}
