import { useEffect, useMemo, useRef, useState } from 'react'
import { PipecatClient, RTVIEvent } from '@pipecat-ai/client-js'
import {
  ProtobufFrameSerializer,
  WebSocketTransport,
} from '@pipecat-ai/websocket-transport'
import './App.css'

const ROUND_OPTIONS = [5, 10, 15, 20]

const INITIAL_GAME_STATE = {
  score: 0,
  round: 0,
  total_rounds: 10,
  current_word: '',
  last_result: '',
  game_over: false,
  session_active: false,
}

export default function App() {
  const [rounds, setRounds] = useState(10)
  const [status, setStatus] = useState('Disconnected')
  const [logs, setLogs] = useState([])
  const [gameState, setGameState] = useState(INITIAL_GAME_STATE)
  const [isConnecting, setIsConnecting] = useState(false)
  const [isConnected, setIsConnected] = useState(false)

  const clientRef = useRef(null)
  const audioRef = useRef(null)
  const pollRef = useRef(null)

  const wsUrl = useMemo(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${protocol}//${window.location.host}/ws?total_rounds=${rounds}`
  }, [rounds])

  const pushLog = (message) => {
    setLogs((prev) => [
      ...prev,
      {
        id: `${Date.now()}-${prev.length}`,
        message,
        timestamp: new Date().toISOString(),
      },
    ])
  }

  const updateStatus = (nextStatus) => {
    setStatus(nextStatus)
    pushLog(`Status: ${nextStatus}`)
  }

  const attachAudioTrack = (track) => {
    const audioEl = audioRef.current
    if (!audioEl) return

    pushLog(
      `Incoming audio track: id=${track.id} readyState=${track.readyState} muted=${track.muted}`
    )

    const currentStream = audioEl.srcObject
    if (currentStream?.getAudioTracks?.()[0]?.id === track.id) {
      return
    }

    track.onmute = () => pushLog(`Audio track muted: ${track.id}`)
    track.onunmute = () => pushLog(`Audio track unmuted: ${track.id}`)
    track.onended = () => pushLog(`Audio track ended: ${track.id}`)

    audioEl.srcObject = new MediaStream([track])
    audioEl
      .play()
      .then(() => pushLog('Audio playback started'))
      .catch((error) => pushLog(`Audio playback blocked: ${error.message}`))
    pushLog('Attached bot audio track')
  }

  const setupMediaTracks = () => {
    const client = clientRef.current
    if (!client) return

    const tracks = client.tracks()
    if (tracks.bot?.audio) {
      attachAudioTrack(tracks.bot.audio)
    }
  }

  const startPollingGameState = () => {
    clearInterval(pollRef.current)
    pollRef.current = setInterval(async () => {
      try {
        const response = await fetch('/game-state')
        const nextState = await response.json()
        setGameState(nextState)
      } catch {
        // ignore transient polling failures
      }
    }, 700)
  }

  const stopPollingGameState = () => {
    clearInterval(pollRef.current)
    pollRef.current = null
  }

  const cleanupAudio = () => {
    const audioEl = audioRef.current
    if (!audioEl?.srcObject?.getAudioTracks) return

    audioEl.srcObject.getAudioTracks().forEach((track) => track.stop())
    audioEl.srcObject = null
  }

  const disconnect = async () => {
    stopPollingGameState()

    const client = clientRef.current
    if (!client) {
      cleanupAudio()
      setIsConnected(false)
      setIsConnecting(false)
      return
    }

    try {
      await client.disconnect()
    } catch (error) {
      pushLog(`Error disconnecting: ${error.message}`)
    } finally {
      clientRef.current = null
      cleanupAudio()
      setIsConnected(false)
      setIsConnecting(false)
    }
  }

  const connect = async () => {
    if (isConnecting || isConnected) return

    setLogs([])
    setGameState({ ...INITIAL_GAME_STATE, total_rounds: rounds })
    setIsConnecting(true)
    updateStatus('Connecting')

    const client = new PipecatClient({
      transport: new WebSocketTransport({
        serializer: new ProtobufFrameSerializer(),
        recorderSampleRate: 16000,
        playerSampleRate: 16000,
      }),
      enableMic: true,
      enableCam: false,
      callbacks: {
        onConnected: () => {
          setIsConnected(true)
          setIsConnecting(false)
          updateStatus('Connected')
          startPollingGameState()
        },
        onDisconnected: () => {
          updateStatus('Disconnected')
          setIsConnected(false)
          setIsConnecting(false)
          stopPollingGameState()
          pushLog('Client disconnected')
        },
        onBotReady: (data) => {
          pushLog(`Bot ready: ${JSON.stringify(data)}`)
          setupMediaTracks()
        },
        onUserStartedSpeaking: () => {
          const transport = clientRef.current?._transport
          transport?._mediaManager?.userStartedSpeaking?.()
        },
        onUserTranscript: (data) => {
          if (data.final) {
            pushLog(`User: ${data.text}`)
          }
        },
        onBotTranscript: (data) => {
          pushLog(`Bot: ${data.text}`)
        },
        onTransportStateChange: (nextState) => {
          pushLog(`Transport: ${nextState}`)
        },
        onMessageError: (error) => {
          pushLog(`Message error: ${error.message}`)
          console.error('Message error:', error)
        },
        onError: (error) => {
          pushLog(`Error: ${error.message}`)
          console.error('Error:', error)
        },
      },
    })

    clientRef.current = client

    client.on(RTVIEvent.TrackStarted, (track, participant) => {
      if (!participant?.local && track.kind === 'audio') {
        attachAudioTrack(track)
      }
    })

    client.on(RTVIEvent.TrackStopped, (track, participant) => {
      pushLog(
        `Track stopped: ${track.kind} from ${participant?.name || 'unknown'}`
      )
    })

    try {
      pushLog('Initializing devices...')
      await client.initDevices()

      pushLog(`Connecting to ${wsUrl}`)
      await client.connect({ wsUrl })

      window.pcClient = client
    } catch (error) {
      pushLog(`Error connecting: ${error.message}`)
      updateStatus('Error')
      await disconnect()
    }
  }

  useEffect(() => {
    const audioEl = audioRef.current
    if (audioEl) {
      audioEl.playsInline = true
      audioEl.onplay = () => pushLog('Audio element play event')
      audioEl.onpause = () => pushLog('Audio element pause event')
      audioEl.onerror = () => pushLog('Audio element error')
      audioEl.onloadedmetadata = () => pushLog('Audio metadata loaded')
    }

    return () => {
      disconnect()
    }
  }, [])

  return (
    <div className="app-shell">
      <audio ref={audioRef} autoPlay />

      <section className="panel hero-panel">
        <p className="eyebrow">Spell Bee Bot</p>
        <h1>Pipecat WebSocket Client</h1>
        <p className="lede">
          This UI connects the browser to your FastAPI Pipecat websocket at
          <code> /ws</code> using the official Pipecat JS client transport.
        </p>

        <div className="controls">
          <label className="field" htmlFor="rounds">
            <span>Rounds</span>
            <select
              id="rounds"
              value={rounds}
              onChange={(event) => setRounds(Number(event.target.value))}
              disabled={isConnected || isConnecting}
            >
              {ROUND_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>

          <div className="button-row">
            <button
              className="btn btn-primary"
              type="button"
              onClick={connect}
              disabled={isConnecting || isConnected}
            >
              {isConnecting ? 'Connecting...' : 'Connect'}
            </button>
            <button
              className="btn btn-secondary"
              type="button"
              onClick={disconnect}
              disabled={!isConnecting && !isConnected}
            >
              Disconnect
            </button>
          </div>
        </div>

        <div className="status-row">
          <span className="status-label">Status</span>
          <strong>{status}</strong>
        </div>
      </section>

      <section className="panel game-panel">
        <div className="panel-header">
          <h2>Live Game State</h2>
          <span className={gameState.session_active ? 'pill live' : 'pill'}>
            {gameState.session_active ? 'Session Active' : 'Idle'}
          </span>
        </div>

        <div className="stats-grid">
          <article className="stat-card">
            <span>Round</span>
            <strong>
              {gameState.round || 0} / {gameState.total_rounds}
            </strong>
          </article>
          <article className="stat-card">
            <span>Score</span>
            <strong>{gameState.score}</strong>
          </article>
          <article className="stat-card">
            <span>Current word</span>
            <strong>{gameState.current_word || 'Waiting...'}</strong>
          </article>
          <article className="stat-card">
            <span>Last result</span>
            <strong>{gameState.last_result || 'None yet'}</strong>
          </article>
        </div>
      </section>

      <section className="panel log-panel">
        <div className="panel-header">
          <h2>Debug Log</h2>
          <span className="pill">{logs.length} entries</span>
        </div>

        <div className="log-list" id="debug-log">
          {logs.length === 0 ? (
            <p className="empty-state">No events yet.</p>
          ) : (
            logs.map((entry) => (
              <div
                key={entry.id}
                className={`log-entry ${
                  entry.message.startsWith('User: ')
                    ? 'user'
                    : entry.message.startsWith('Bot: ')
                      ? 'bot'
                      : ''
                }`}
              >
                <time>{entry.timestamp}</time>
                <span>{entry.message}</span>
              </div>
            ))
          )}
        </div>
      </section>
    </div>
  )
}
