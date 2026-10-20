// Built by vite.config.ts (evidenceFront): the few logged values the first download needs. Same files, same numbers as virtual:evidence.
declare module 'virtual:evidence-front' {
  import type full from 'virtual:evidence'
  type E = typeof full
  const front: {
    blind5: E['blind5']
    feedback: E['feedback']
    claudeSpend: E['claudeSpend']
    aws: { loadtest: E['aws']['loadtest'] }
    drawing: { text: E['drawing']['text']; textGen: E['drawing']['textGen']; genFashion: E['drawing']['genFashion']; genResnet: E['drawing']['genResnet'] }
    findings: { blind4: E['findings']['blind4'] }
    agreement: E['agreement']
  }
  export default front
}
