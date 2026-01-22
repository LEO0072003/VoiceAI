import { useState, useEffect, useRef } from 'react'
import './Avatar.css'

// Viseme to mouth shape mapping
const VISEME_SHAPES = {
  'sil': 'closed',      // Silence
  'PP': 'closed',       // p, b, m
  'FF': 'narrow',       // f, v
  'TH': 'narrow',       // th
  'DD': 'narrow',       // t, d
  'kk': 'narrow',       // k, g
  'CH': 'medium',       // ch, j, sh
  'SS': 'narrow',       // s, z
  'nn': 'narrow',       // n, l
  'RR': 'medium',       // r
  'aa': 'wide',         // a
  'E': 'medium',        // e
  'I': 'narrow',        // i
  'O': 'round',         // o
  'U': 'round',         // u
  // Fallback mappings
  'default': 'closed'
}

// Map Cartesia viseme IDs to shapes
const mapVisemeToShape = (visemeId) => {
  if (!visemeId) return 'closed'
  // Cartesia uses different viseme IDs, map them appropriately
  const id = visemeId.toString().toLowerCase()
  if (id.includes('sil') || id === '0') return 'closed'
  if (['p', 'b', 'm', '1', '2'].some(v => id.includes(v))) return 'closed'
  if (['f', 'v', '3'].some(v => id.includes(v))) return 'narrow'
  if (['th', '4'].some(v => id.includes(v))) return 'narrow'
  if (['t', 'd', 's', 'z', 'n', 'l', '5', '6', '7', '8'].some(v => id.includes(v))) return 'narrow'
  if (['k', 'g', '9'].some(v => id.includes(v))) return 'narrow'
  if (['ch', 'j', 'sh', '10', '11'].some(v => id.includes(v))) return 'medium'
  if (['r', '12'].some(v => id.includes(v))) return 'medium'
  if (['a', 'aa', '13', '14'].some(v => id.includes(v))) return 'wide'
  if (['e', 'eh', '15'].some(v => id.includes(v))) return 'medium'
  if (['i', 'ih', '16'].some(v => id.includes(v))) return 'narrow'
  if (['o', 'oh', '17', '18'].some(v => id.includes(v))) return 'round'
  if (['u', 'uh', '19', '20', '21'].some(v => id.includes(v))) return 'round'
  return 'medium'
}

function Avatar({ 
  state = 'idle', // idle, listening, speaking, thinking, ended
  visemes = [],
  audioLevel = 0,
  isPlaying = false
}) {
  const [mouthShape, setMouthShape] = useState('closed')
  const [eyeState, setEyeState] = useState('open')
  const [currentVisemeIndex, setCurrentVisemeIndex] = useState(0)
  const animationRef = useRef(null)
  const startTimeRef = useRef(null)

  // Handle viseme animation when speaking
  useEffect(() => {
    if (state === 'speaking' && isPlaying && visemes && visemes.length > 0) {
      startTimeRef.current = Date.now()
      setCurrentVisemeIndex(0)
      
      const animateVisemes = () => {
        const elapsed = Date.now() - startTimeRef.current
        
        // Find current viseme based on elapsed time
        let currentIndex = 0
        for (let i = 0; i < visemes.length; i++) {
          const viseme = visemes[i]
          const startMs = viseme.start || viseme.time || (i * 80)
          if (elapsed >= startMs) {
            currentIndex = i
          } else {
            break
          }
        }
        
        if (currentIndex < visemes.length) {
          const viseme = visemes[currentIndex]
          const shape = mapVisemeToShape(viseme.id || viseme.viseme)
          setMouthShape(shape)
          setCurrentVisemeIndex(currentIndex)
          animationRef.current = requestAnimationFrame(animateVisemes)
        } else {
          setMouthShape('closed')
        }
      }
      
      animationRef.current = requestAnimationFrame(animateVisemes)
      
      return () => {
        if (animationRef.current) {
          cancelAnimationFrame(animationRef.current)
        }
      }
    } else if (state === 'speaking' && isPlaying) {
      // Fallback: animate mouth based on simple pattern when no visemes
      let frame = 0
      const shapes = ['closed', 'narrow', 'medium', 'wide', 'medium', 'narrow']
      
      const animate = () => {
        setMouthShape(shapes[frame % shapes.length])
        frame++
        animationRef.current = setTimeout(() => {
          animationRef.current = requestAnimationFrame(animate)
        }, 100)
      }
      
      animate()
      
      return () => {
        if (animationRef.current) {
          cancelAnimationFrame(animationRef.current)
          clearTimeout(animationRef.current)
        }
        setMouthShape('closed')
      }
    } else {
      setMouthShape('closed')
    }
  }, [state, isPlaying, visemes])

  // Eye blinking animation
  useEffect(() => {
    const blinkInterval = setInterval(() => {
      setEyeState('closed')
      setTimeout(() => setEyeState('open'), 150)
    }, 3000 + Math.random() * 2000)
    
    return () => clearInterval(blinkInterval)
  }, [])

  // Mouth animation for listening state (based on audio level)
  useEffect(() => {
    if (state === 'listening' && audioLevel > 20) {
      const shapes = ['narrow', 'medium', 'wide']
      const index = Math.min(Math.floor(audioLevel / 35), 2)
      setMouthShape(shapes[index])
    } else if (state === 'listening') {
      setMouthShape('closed')
    }
  }, [state, audioLevel])

  // Get mouth path based on shape
  const getMouthPath = () => {
    switch (mouthShape) {
      case 'closed':
        return 'M 35,75 Q 50,78 65,75' // Slight smile
      case 'narrow':
        return 'M 38,72 Q 50,80 62,72' // Small open
      case 'medium':
        return 'M 35,70 Q 50,85 65,70' // Medium open
      case 'wide':
        return 'M 32,68 Q 50,90 68,68' // Wide open
      case 'round':
        return 'M 40,70 Q 50,82 60,70 Q 55,78 50,80 Q 45,78 40,70' // Round O shape
      default:
        return 'M 35,75 Q 50,78 65,75'
    }
  }

  // Get eye path
  const getEyePath = (isLeft) => {
    const x = isLeft ? 35 : 65
    if (eyeState === 'closed') {
      return `M ${x - 6},50 Q ${x},50 ${x + 6},50`
    }
    return `M ${x - 6},50 Q ${x},44 ${x + 6},50 Q ${x},56 ${x - 6},50`
  }

  return (
    <div className={`avatar-container ${state}`}>
      {/* Glow effect based on state */}
      <div className="avatar-glow"></div>
      
      {/* Main avatar SVG */}
      <svg 
        viewBox="0 0 100 100" 
        className="avatar-svg"
      >
        {/* Head/Face */}
        <defs>
          <linearGradient id="faceGradient" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#ffecd2" />
            <stop offset="100%" stopColor="#fcb69f" />
          </linearGradient>
          <linearGradient id="hairGradient" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#4a3728" />
            <stop offset="100%" stopColor="#2d1f14" />
          </linearGradient>
          <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="2" stdDeviation="2" floodOpacity="0.2"/>
          </filter>
        </defs>
        
        {/* Hair back */}
        <ellipse cx="50" cy="35" rx="38" ry="30" fill="url(#hairGradient)" />
        
        {/* Face */}
        <ellipse 
          cx="50" cy="50" rx="35" ry="40" 
          fill="url(#faceGradient)" 
          filter="url(#shadow)"
        />
        
        {/* Hair front */}
        <path 
          d="M 15,40 Q 20,15 50,12 Q 80,15 85,40 Q 75,25 50,22 Q 25,25 15,40" 
          fill="url(#hairGradient)"
        />
        
        {/* Eyebrows */}
        <path 
          d="M 26,42 Q 35,38 44,42" 
          stroke="#3d2314" 
          strokeWidth="2" 
          fill="none"
          strokeLinecap="round"
        />
        <path 
          d="M 56,42 Q 65,38 74,42" 
          stroke="#3d2314" 
          strokeWidth="2" 
          fill="none"
          strokeLinecap="round"
        />
        
        {/* Eyes */}
        <path 
          d={getEyePath(true)} 
          fill="#fff" 
          stroke="#2d1f14" 
          strokeWidth="1"
        />
        <path 
          d={getEyePath(false)} 
          fill="#fff" 
          stroke="#2d1f14" 
          strokeWidth="1"
        />
        
        {/* Pupils */}
        {eyeState === 'open' && (
          <>
            <circle cx="35" cy="50" r="3" fill="#2d1f14">
              <animate 
                attributeName="cx" 
                values="34;36;35;34" 
                dur="4s" 
                repeatCount="indefinite"
              />
            </circle>
            <circle cx="65" cy="50" r="3" fill="#2d1f14">
              <animate 
                attributeName="cx" 
                values="64;66;65;64" 
                dur="4s" 
                repeatCount="indefinite"
              />
            </circle>
            {/* Eye highlights */}
            <circle cx="36" cy="48" r="1" fill="#fff" />
            <circle cx="66" cy="48" r="1" fill="#fff" />
          </>
        )}
        
        {/* Nose */}
        <path 
          d="M 50,52 L 48,62 Q 50,64 52,62 L 50,52" 
          fill="none" 
          stroke="#e0a080" 
          strokeWidth="1.5"
          strokeLinecap="round"
        />
        
        {/* Mouth */}
        <path 
          d={getMouthPath()} 
          fill={mouthShape === 'closed' ? 'none' : '#c44'}
          stroke="#c44" 
          strokeWidth="2"
          strokeLinecap="round"
          className="avatar-mouth"
        />
        
        {/* Cheeks (blush) */}
        <ellipse cx="25" cy="60" rx="6" ry="4" fill="#ffb6c1" opacity="0.4" />
        <ellipse cx="75" cy="60" rx="6" ry="4" fill="#ffb6c1" opacity="0.4" />
        
        {/* Ears */}
        <ellipse cx="15" cy="50" rx="5" ry="8" fill="url(#faceGradient)" />
        <ellipse cx="85" cy="50" rx="5" ry="8" fill="url(#faceGradient)" />
      </svg>
      
      {/* State indicator ring */}
      <div className="state-ring">
        {state === 'listening' && (
          <div 
            className="audio-level-ring"
            style={{ 
              transform: `scale(${1 + audioLevel / 150})`,
              opacity: 0.3 + (audioLevel / 200)
            }}
          />
        )}
      </div>
      
      {/* Status text */}
      <div className="avatar-status">
        {state === 'idle' && '😴 Ready'}
        {state === 'listening' && '👂 Listening...'}
        {state === 'thinking' && '🤔 Thinking...'}
        {state === 'speaking' && '🗣️ Speaking...'}
        {state === 'ended' && '👋 Call Ended'}
      </div>
    </div>
  )
}

export default Avatar
