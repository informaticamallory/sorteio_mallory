/* Service worker do Portal do Colaborador (Sorteios Mallory).
 *
 * Só recebe notificações push e abre o cartão ao tocar nelas.
 * Não intercepta requisições e não guarda cache: o restante do sistema
 * (painel, telão, Recepção) funciona exatamente como sem ele.
 */

self.addEventListener('install', () => self.skipWaiting())
self.addEventListener('activate', (evento) => evento.waitUntil(self.clients.claim()))

self.addEventListener('push', (evento) => {
  let dados = {}
  try {
    dados = evento.data ? evento.data.json() : {}
  } catch (_erro) {
    dados = { mensagem: evento.data ? evento.data.text() : '' }
  }
  const titulo = dados.titulo || 'Sorteios Mallory'
  evento.waitUntil(
    (async () => {
      await self.registration.showNotification(titulo, {
        body: dados.mensagem || '',
        icon: '/marca/icone-192.png',
        badge: '/marca/icone-192.png',
        tag: dados.tag || 'sorteio',
        data: { url: dados.url || '/minha-area' },
      })
      // Portal aberto: atualiza o cartão na hora.
      const janelas = await self.clients.matchAll({ type: 'window', includeUncontrolled: true })
      for (const janela of janelas) janela.postMessage({ tipo: 'push_recebido' })
    })(),
  )
})

self.addEventListener('notificationclick', (evento) => {
  evento.notification.close()
  const destino = (evento.notification.data && evento.notification.data.url) || '/minha-area'
  evento.waitUntil(
    (async () => {
      const janelas = await self.clients.matchAll({ type: 'window', includeUncontrolled: true })
      for (const janela of janelas) {
        if (new URL(janela.url).pathname.startsWith('/minha-area') && 'focus' in janela) {
          await janela.focus()
          if ('navigate' in janela) await janela.navigate(destino)
          return
        }
      }
      await self.clients.openWindow(destino)
    })(),
  )
})
