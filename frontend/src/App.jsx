import { useState } from 'react'
import './App.css'

function App() {
  const [count, setCount] = useState(0)

  return (
    <main className="app">
      <h1>Hackathon BBVA · Equipo 7</h1>
      <button onClick={() => setCount((c) => c + 1)}>count is {count}</button>
      <p>
        Edit <code>src/App.jsx</code> and save to see changes.
      </p>
    </main>
  )
}

export default App
