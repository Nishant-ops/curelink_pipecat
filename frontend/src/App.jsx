import { useEffect, useMemo, useRef, useState } from 'react'
import { PipecatClient, RTVIEvent } from '@pipecat-ai/client-js'
import {
  ProtobufFrameSerializer,
  WebSocketTransport,
} from '@pipecat-ai/websocket-transport'
import './App.css'
import {
  AUDIO_SAMPLE_RATE,
  BOT_AVATAR_INITIALS,
  BOT_DISPLAY_NAME,
  GAME_STATE_PATH,
  LABEL_CORRECT,
  LABEL_CORRECT_ICON,
  LABEL_INCORRECT,
  LABEL_INCORRECT_ICON,
  POLL_INTERVAL_MS,
  RESULT_CORRECT,
  WS_PATH,
} from './constants'

export default function App() {
  const [joined, setJoined] = useState(false)
  const [joining, setJoining] = useState(false)
  const [botSpeaking, setBotSpeaking] = useState(false)
  const [userSpeaking, setUserSpeaking] = useState(false)
  const [gameState, setGameState] = useState(null)
  const [history, setHistory] = useState([])

  const clientRef = useRef(null)
  const audioRef = useRef(null)
  const prevStateRef = useRef(null)

  const wsUrl = useMemo(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${protocol}//${window.location.host}${WS_PATH}`
  }, [])

  // Poll game state while joined
  useEffect(() => {
    if (!joined) return
    const id = setInterval(async () => {
      try {
        const res = await fetch(GAME_STATE_PATH)
        if (!res.ok) return
        const data = await res.json()
        setGameState(data)

        const prev = prevStateRef.current
        // When a round completes (last_result flips to correct/incorrect)
        if (
          data.last_result &&
          data.current_word &&
          prev &&
          (prev.last_result !== data.last_result || prev.current_word !== data.current_word || prev.round !== data.round)
        ) {
          setHistory((h) => {
            // avoid duplicate entries for same word+result
            const last = h[h.length - 1]
            if (last && last.word === data.current_word && last.result === data.last_result) return h
            return [...h, { word: data.current_word, result: data.last_result }]
          })
        }
        prevStateRef.current = data
      } catch {}
    }, POLL_INTERVAL_MS)
    return () => clearInterval(id)
  }, [joined])

  const attachAudioTrack = (track) => {
    const audioEl = audioRef.current
    if (!audioEl) return
    const currentStream = audioEl.srcObject
    if (currentStream?.getAudioTracks?.()[0]?.id === track.id) return
    audioEl.srcObject = new MediaStream([track])
    audioEl.play().catch(() => {})
  }

  const setupMediaTracks = () => {
    const client = clientRef.current
    if (!client) return
    const tracks = client.tracks()
    if (tracks.bot?.audio) attachAudioTrack(tracks.bot.audio)
  }

  const cleanupAudio = () => {
    const audioEl = audioRef.current
    if (!audioEl?.srcObject?.getAudioTracks) return
    audioEl.srcObject.getAudioTracks().forEach((t) => t.stop())
    audioEl.srcObject = null
  }

  const leave = async () => {
    const client = clientRef.current
    if (!client) {
      cleanupAudio()
      setJoined(false)
      setJoining(false)
      return
    }
    try {
      await client.disconnect()
    } catch {}
    finally {
      clientRef.current = null
      cleanupAudio()
      setJoined(false)
      setJoining(false)
      setBotSpeaking(false)
      setUserSpeaking(false)
    }
  }

  const join = async () => {
    if (joining) return
    if (joined) await leave()
    setJoining(true)
    setHistory([])
    setGameState(null)
    prevStateRef.current = null

    const client = new PipecatClient({
      transport: new WebSocketTransport({
        serializer: new ProtobufFrameSerializer(),
        recorderSampleRate: AUDIO_SAMPLE_RATE,
        playerSampleRate: AUDIO_SAMPLE_RATE,
      }),
      enableMic: true,
      enableCam: false,
      callbacks: {
        onConnected: () => {
          setJoined(true)
          setJoining(false)
        },
        onDisconnected: () => {
          setJoined(false)
          setJoining(false)
          setBotSpeaking(false)
          setUserSpeaking(false)
        },
        onBotReady: () => {
          setupMediaTracks()
        },
        onBotStartedSpeaking: () => {
          setBotSpeaking(true)
          // After a user interruption, WavStreamPlayer marks the "default" track as
          // interrupted and silently drops all subsequent audio until cleared.
          // Reset it here so each new bot utterance gets a fresh AudioWorklet stream.
          const player = clientRef.current?._transport?._mediaManager?._wavStreamPlayer
          if (player) player.interruptedTrackIds = {}
        },
        onBotStoppedSpeaking: () => setBotSpeaking(false),
        onUserStartedSpeaking: () => {
          setUserSpeaking(true)
          const transport = clientRef.current?._transport
          transport?._mediaManager?.userStartedSpeaking?.()
        },
        onUserStoppedSpeaking: () => setUserSpeaking(false),
        onError: (error) => console.error('Error:', error),
      },
    })

    clientRef.current = client

    client.on(RTVIEvent.TrackStarted, (track, participant) => {
      if (!participant?.local && track.kind === 'audio') {
        attachAudioTrack(track)
      }
    })

    try {
      await client.initDevices()
      await client.connect({ wsUrl })
      window.pcClient = client
    } catch (error) {
      console.error('Connection error:', error)
      await leave()
    }
  }

  useEffect(() => {
    const audioEl = audioRef.current
    if (audioEl) audioEl.playsInline = true
    return () => { leave() }
  }, [])

  const isActive = joined || gameState?.game_over

  return (
    <div className="shell">
      <audio ref={audioRef} autoPlay />

      <h1 className="title">Spell Bee</h1>

      {/* Score + round panel */}
      {isActive && gameState && (
        <div className="scoreboard">
          <div className="score-block">
            <span className="score-label">Score</span>
            <span className="score-value">{gameState.score} <span className="score-total">/ {gameState.total_rounds}</span></span>
          </div>
          <div className="divider" />
          <div className="score-block">
            <span className="score-label">Round</span>
            <span className="score-value">{gameState.round || '—'} <span className="score-total">/ {gameState.total_rounds}</span></span>
          </div>
          {gameState.last_result && (
            <>
              <div className="divider" />
              <div className={`result-badge ${gameState.last_result}`}>
                {gameState.last_result === RESULT_CORRECT ? LABEL_CORRECT : LABEL_INCORRECT}
              </div>
            </>
          )}
          {gameState.game_over && (
            <div className="game-over-badge">Game Over</div>
          )}
        </div>
      )}

      {!joined && !joining && !gameState?.game_over && (
        <button className="join-btn" onClick={join}>
          Join Game
        </button>
      )}

      {joining && (
        <p className="joining-text">Joining...</p>
      )}

      {gameState?.game_over && !joining && (
        <button className="join-btn" onClick={join}>
          Play Again
        </button>
      )}

      {joined && (
        <div className="participants">
          <div className={`participant ${botSpeaking ? 'speaking' : ''}`}>
            <div className="avatar">
              <span>{BOT_AVATAR_INITIALS}</span>
              <div className="mic-ring" />
            </div>
            <p className="participant-name">{BOT_DISPLAY_NAME}</p>
            <div className="mic-bars">
              {[...Array(4)].map((_, i) => (
                <div key={i} className="bar" style={{ '--i': i }} />
              ))}
            </div>
          </div>

          <div className={`participant ${userSpeaking ? 'speaking' : ''}`}>
            <div className="avatar">
              <span>You</span>
              <div className="mic-ring" />
            </div>
            <p className="participant-name">You</p>
            <div className="mic-bars">
              {[...Array(4)].map((_, i) => (
                <div key={i} className="bar" style={{ '--i': i }} />
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Word history */}
      {history.length > 0 && (
        <div className="history">
          <h2 className="history-title">History</h2>
          <ul className="history-list">
            {[...history].reverse().map((entry, i) => (
              <li key={i} className={`history-item ${entry.result}`}>
                <span className="history-word">{entry.word}</span>
                <span className="history-badge">
                  {entry.result === RESULT_CORRECT ? LABEL_CORRECT_ICON : LABEL_INCORRECT_ICON}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
